# Dependence analyses

StatWorkbench provides six workflows in its Dependence models menu alongside Bivariate Copulas. The selection dialogs use worksheet columns as inputs; blank cells are handled per method, as described below.

## Correlation Matrix

Choose Pearson, Spearman, or Kendall tau-b for two or more variables. The result contains symmetric coefficient, raw p-value, adjusted p-value, and sample-size matrices. Missing rows can be removed separately for each pair or once across all selected columns. Benjamini–Hochberg false-discovery-rate adjustment is the default and is performed across unique off-diagonal pairs. Rank-correlation p-values use SciPy's asymptotic approximation, so small-sample results need care. All three tests assume independent observations; serial and clustered designs need an appropriate model.

## Partial Correlation

Choose X, Y, and optionally one or more numeric controls. The procedure regresses X and Y separately on an intercept and the controls, then correlates the residuals. The t test uses degrees of freedom `n − rank(intercept, controls) − 1`, which reduces to `n − k − 2` for `k` independent controls. The interval uses the Fisher z approximation. This describes linear adjustment; it does not test general conditional independence.

## Distance Correlation

For two numeric variables, the procedure double-centers their absolute-distance matrices and reports the biased sample distance-correlation estimator. Unlike Pearson correlation, it can detect nonlinear association. The optional permutation test shuffles one variable, uses the plus-one p-value correction, and requires exchangeable independent rows. A computation budget bounds matrix size and permutation work; use zero permutations to calculate the measure only.

## Binned Mutual Information

The procedure assigns each variable to empirical quantile bins and calculates plug-in mutual information in nats. It also reports normalized MI, defined as mutual information divided by the geometric mean of the marginal entropies. Binning trades detail for stability, ties can merge bins, and the plug-in estimate has positive finite-sample bias. A permutation test provides a null comparison for the selected binning, not a bin-free dependence test.

## Empirical Tail Co-exceedance

At a requested marginal tail probability, the procedure reports upper–upper, lower–lower, upper–lower, and lower–upper events. Each row gives realized marginal rates, joint and conditional rates, and the independence benchmark calculated from the realized marginal rates. Ties may make realized rates differ from the nominal threshold. These finite-threshold descriptive values are not asymptotic copula tail-dependence coefficients.

## Lead–Lag Cross-Correlation

The procedure reports Pearson correlation across a symmetric range of integer lags. Positive lag `k` means `X(t)` is compared with `Y(t+k)`, so X leads Y by k worksheet rows. It retains row alignment when values are missing and reports the aligned sample size at each lag. The chart is descriptive: serial dependence and searching across lags make ordinary single-lag significance claims inappropriate, so the procedure does not report p-values.

## Validation

The numerical fixtures are in `tests/test_dependence.py`; they include nonlinear synthetic relationships, a shared-control example, seeded permutations, all four tail quadrants, lag direction, missing values, option validation, registry exposure, and strict worker JSON serialization. Run them with:

```sh
PYTHONPATH=. .venv/bin/python -m unittest tests.test_dependence -v
```

Markov chains and stochastic-process diagnostics are in the Time Series category, since they model ordered state transitions rather than pairwise association. See [Markov Chain & Ergodicity](stochastic-processes.md). The related bivariate copula fit, density, tail-coefficient, holdout, and simulation limits are described in [copulas](copulas.md).
