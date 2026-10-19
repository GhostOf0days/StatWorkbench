"""Histogram bin selection shared by descriptive and frequency reports."""
from __future__ import annotations
import math
import numpy as np


def neat_bounds(low, high, target_count):
    """Return lower/upper boundary, interval width and adjusted interval count.

    The native choice is a biased nearest 1/2/5 decimal width: normalized
    thresholds are strictly >1.4, >2.8 and >7. It is not ceiling rounding.
    The 1e-7 tolerance is measured in units of the chosen width.
    """
    low, high = float(low), float(high)
    if not (math.isfinite(low) and math.isfinite(high)) or high <= low:
        raise ValueError('Neat boundaries require finite, increasing extrema.')
    target_count = max(1, int(target_count))
    span = high-low
    magnitude = max(abs(low), abs(high))
    if span >= magnitude*.4*target_count*2e-16*3:
        desired = span/target_count
    else:
        desired = (magnitude/10+9 if magnitude > 10 else magnitude)*.75
    desired = min(max(desired, 1e-9), np.finfo(float).max/1000)
    scale = 10.**math.floor(math.log10(desired))
    # Preserve native strict comparisons rather than rounding thresholds.
    width = scale
    if 2*scale-desired < (desired-scale)*1.5:
        width = 2*scale
        if 5*scale-desired < (desired-2*scale)*2.75:
            width = 5*scale
            if 10*scale-desired < (desired-5*scale)*1.5:
                width = 10*scale
    lower_index = math.floor(low/width+1e-7)
    upper_index = math.ceil(high/width-1e-7)
    # These tolerance corrections also protect translated ranges from a
    # boundary being rounded onto the wrong side of an observed endpoint.
    while lower_index*width > low+width*1e-7:
        lower_index -= 1
    while upper_index*width < high-width*1e-7:
        upper_index += 1
    count = int(upper_index+.5-lower_index)
    if count < 1:
        # The callers handle constant series separately. For a sub-tolerance
        # nonconstant range keep one enclosing representable interval.
        count = 1
        upper_index = lower_index+1
    return min(low, lower_index*width), max(high, upper_index*width), width, count


def frequency_edges(values, requested=0, closed='left', *, histogram=False):
    """Native frequency-table boundaries, including the open endpoint guard.

    Continuous-frequency retries retain the requested count; Histogram retries
    feed the previously adjusted count back into the neat-boundary helper.
    """
    values = np.asarray(values, dtype=float)
    low, high = float(np.min(values)), float(np.max(values))
    if low == high:
        return np.array([low, high])
    target = int(requested) or int(1+math.log2(len(values)))
    lower, upper, width, count = neat_bounds(low, high, target)
    if closed == 'right' and lower == low:
        lower, upper, width, count = neat_bounds(low-(high-low)*.01, high,
                                                count if histogram else target)
    if closed == 'left' and upper == high:
        lower, upper, width, count = neat_bounds(low, high+(high-low)*.01,
                                                count if histogram else target)
    return lower+np.arange(count+1)*width


def descriptive_histogram(values, requested=0):
    """Native descriptive histogram bins and final catch-all bin counts."""
    values = np.asarray(values, dtype=float)
    count = min(int(requested), len(values)) if requested else math.ceil(1+math.log2(len(values)))
    low, high = float(np.min(values)), float(np.max(values))
    if low == high:
        return np.array([len(values)]), np.array([low, high])
    low, _, width, count = neat_bounds(low, high, count)
    edges = low+np.arange(count+1)*width
    indices = np.clip(((values-low)/width).astype(int), 0, count-1)
    return np.bincount(indices, minlength=count), edges
