# Numerical methods

StatWorkbench uses NumPy, SciPy, pandas, statsmodels, and scikit-learn for numerical operations where suitable. Analysis modules combine these tools with explicit input validation, worksheet-aware data handling, and result tables designed for the desktop interface.

The method used by each procedure is described in its catalog entry and result notes. Important choices include missing-value handling, tie treatment, variance estimators, degrees of freedom, confidence intervals, and random-number seeding. Users should review these choices before interpreting results.

The code favors transparent, reproducible procedures and bounded computation. Permutation tests and simulation accept seeds; analyses that require more time or memory impose explicit limits. Invalid, degenerate, or unsupported inputs should produce an actionable error or a stated limitation rather than a fabricated statistic.

See the feature guides for [Dependence](../../docs/dependence.md), [Copulas](../../docs/copulas.md), and [stochastic processes](../../docs/stochastic-processes.md).
