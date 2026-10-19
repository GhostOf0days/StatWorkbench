"""Independent implementation of the observed descriptive-chart grid policy.

The compatibility facts are an outward 1/2/5 grid, a ten-division budget,
and a second fixed-bound pass for tick spacing. See the chart-axis tests.
"""
import math


def _exponent(value):
    if abs(value) < 1e-12:
        return 0
    exponent = math.log10(abs(value))
    upper = math.ceil(exponent)
    return upper if abs(exponent-upper) < 1e-12 else math.floor(exponent)


def nice_range(low, high, divisions=10, fixed=False):
    """Return bounds and spacing, retaining native binary64 boundary behavior."""
    low, high = float(low), float(high)
    if not math.isfinite(low) or not math.isfinite(high) or high < low:
        raise ValueError('Chart limits must be finite and ordered.')
    if abs(high-low) < 1e-12 and abs(high) < 1e-12:
        return 0., 1., 1.
    try:
        step = 10.**(max(_exponent(low), _exponent(high))+1)
        def bounds(unit):
            if fixed:
                return low, high
            return ((math.ceil(low/unit)-1)*unit if low else 0.,
                    (math.floor(high/unit)+1)*unit)
        left, right = bounds(step)
        for _ in range(101):
            mantissa = step/(10.**_exponent(step))
            if abs(mantissa-5) < 1e-12:
                smaller = step*.4
            elif abs(mantissa-1) < 1e-12 or abs(mantissa-2) < 1e-12:
                smaller = step*.5
            else:
                break
            if not smaller or not math.isfinite(smaller):
                break
            if (right-left)/smaller > divisions:
                return left, right if right != left else left+1., step
            step = smaller
            left, right = bounds(step)
    except (OverflowError, ZeroDivisionError):
        pass
    # Native reduction can fail at extreme magnitudes. Keep a finite usable
    # chart, without claiming matching ticks outside the verified range.
    if low == high:
        high = math.nextafter(low, math.inf) if abs(low) > 1e15 else low+1.
    return low, high, (high-low)/max(1, divisions)


def descriptive_qq_axes(x, y):
    xmin, xmax, _ = nice_range(min(x), max(x))
    ymin, ymax, _ = nice_range(min(y), max(y))
    xdivisions = 25 if abs(xmin) < 1e-12 or abs(xmin-1) < 1e-12 else 10
    return dict(xMin=xmin, xMax=xmax, yMin=ymin, yMax=ymax,
                xMajorUnit=nice_range(xmin, xmax, xdivisions, fixed=True)[2],
                yMajorUnit=nice_range(ymin, ymax, fixed=True)[2], clip=True)
