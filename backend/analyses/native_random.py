"""Seeded MT19937 random-number generation and distribution transforms."""
import numpy as np


class NativeRandom:
    def __init__(self, seed):
        self.seed = int(seed) & 0xffffffff
        self._random = np.random.RandomState(self.seed)

    def words(self, count):
        return self._random.randint(0, 2**32, size=count, dtype=np.uint32)

    def uniform(self, count):
        return self.words(count).astype(float) * (1.0 / 2**32)

    def integers(self, low, high, count):
        # Multiply-high mapping uses an exclusive upper bound.
        # Keep the interval signed 32-bit to avoid silent overflow.
        width = int(high) - int(low)
        if not (-2**31 <= low < high <= 2**31-1) or width > 2**31-1:
            raise ValueError('Discrete bounds and interval width must fit signed 32-bit integers.')
        return ((self.words(count).astype(np.uint64)*width) >> 32).astype(np.int64)+low

    def normal(self, count):
        """Polar normals: one output per accepted pair, no cached second value."""
        output = np.empty(count)
        offset = 0
        while offset < count:
            # At most one accepted value per pair, so no unused accepted values
            # are discarded when changing call/chunk size.
            pairs = 2*self.uniform(2*min(count-offset, 65536)).reshape(-1, 2)-1
            radius = pairs[:, 0]**2+pairs[:, 1]**2
            valid = radius < 1
            selected = radius[valid]
            with np.errstate(divide='ignore', invalid='ignore'):
                values = pairs[valid, 0]*np.sqrt(-2*np.log(selected)/selected)
            output[offset:offset+len(values)] = values
            offset += len(values)
        return output

    def sum_squares(self, count, df, df2=None):
        """Sum squared normals, or their unscaled ratio, in observation order."""
        width = df+(df2 or 0)
        output = np.empty(count)
        # Bound temporary allocations independently of requested degrees of
        # freedom. A row with very large df is accumulated in bounded chunks.
        if width > 65536:
            for index in range(count):
                sums = []
                for degrees in ([df, df2] if df2 else [df]):
                    total = 0.0
                    for start in range(0, degrees, 65536):
                        values = self.normal(min(degrees-start, 65536))
                        total += float(np.dot(values, values))
                    sums.append(total)
                output[index] = sums[0] if not df2 else sums[0]/sums[1]
        else:
            chunk = max(1, 65536//width)
            for start in range(0, count, chunk):
                length = min(count-start, chunk)
                squares = self.normal(length*width).reshape(length, width)**2
                # cumsum preserves the observed per-row accumulation order.
                numerators = np.cumsum(squares[:, :df], axis=1)[:, -1]
                if df2:
                    numerators /= np.cumsum(squares[:, df:], axis=1)[:, -1]
                output[start:start+length] = numerators
        return output
