# Bivariate copulas

`Dependence models → Bivariate Copulas` fits and simulates bivariate copula models through the `copula.bivariate` analysis.

Select two numeric columns with 20–20,000 complete pairs. Average ranks divided by `N+1` put the observations inside the open unit square. Missing, nonnumeric and nonfinite pairs are removed together; tied values receive average ranks and an explicit warning because continuous copula likelihoods are only approximate for discrete data. Constant variables and perfect rank dependence are rejected.

## Models and fitting

| Family | Parameters and supported bounds | Dependence |
| --- | --- | --- |
| Independence | No fitted parameters | Baseline |
| Gaussian | `rho ∈ [-0.995, 0.995]` | Positive or negative; zero asymptotic tail dependence |
| Student t | `rho ∈ [-0.995, 0.995]`, `df ∈ [2.01, 100]` | Positive or negative; symmetric nonzero tail dependence |
| Clayton | `theta ∈ [0, 30]` | Positive lower-tail dependence; zero is independence |
| Frank | `theta ∈ [-35, 35]` | Positive or negative; zero is independence |
| Gumbel | `theta ∈ [1, 25]` | Positive upper-tail dependence; one is independence |

Fits maximize the **copula pseudo-likelihood** of rank-transformed observations. Scalar models use bounded optimization; Student t uses bounded two-parameter optimization with two starts. Failed fits are identified rather than assigned fabricated statistics. Parameters at an imposed bound are labeled and the selected boundary fit produces a warning.

“Compare all” chooses the lowest BIC among converged fits, including independence. Explicit family selection still reports independence and Gaussian challenger models. AIC and BIC use the copula parameter count; these rank-based criteria do not assess the marginal models or establish overall goodness of fit. No parameter standard errors or goodness-of-fit p-values are claimed.

## Diagnostics

The report includes observed Kendall tau-b and Spearman rho, fitted log pseudo-likelihood, AIC/BIC, and asymptotic upper/lower tail coefficients. The Student t coefficient is `2 T_(df+1)(-sqrt((df+1)(1-rho)/(1+rho)))`.

At a user-selected tail probability of 1%–25%, a separate finite-tail table compares the observed joint-tail frequency with 10,000 seeded model draws and reports Monte Carlo standard error. These finite probabilities are distinct from asymptotic tail coefficients. Fewer than five observed joint-tail events produces an imprecision warning.

With at least 40 pairs, optional chronological diagnostics use the first 80% for fitting and the final 20% for scoring. **Holdout probabilities are transformed using the training marginal empirical distributions only.** They never use future values to rank the training set. Negative selected-family holdout log density warns that independence performed better. Separate first-half and second-half fits report parameter and Kendall tau drift; a tau difference above 0.3 raises a stationarity warning. Row order therefore matters: sort by time first for a temporal interpretation. These are descriptive checks, not formal significance tests or a guarantee of future performance.

## Simulation and limits

An optional worksheet contains up to 10,000 seeded pairs, both uniform copula coordinates and values mapped through linearly interpolated empirical quantiles. Simulation does not extrapolate beyond observed marginal extrema. A fixed seed is reproducible within the same scientific runtime and does not change NumPy’s global RNG state.

Gaussian and Student t draws use correlated latent variables. Archimedean draws invert the conditional CDF by bounded vectorized bisection. Stable log-density formulas avoid subtraction failures near the supported parameter limits. Scatter charts show at most the first 2,000 pairs; all pairs remain available in generated worksheet data.

This procedure supports two continuous variables, not higher-dimensional vine copulas, rotated Archimedean families, discrete copula likelihoods, fitted parametric marginals, or automated production risk decisions. Independence/Gaussian remain available when a richer fit is unstable. Users should review holdout and tail diagnostics before choosing a scenario model; the app does not automatically deploy one.

## Validation and implementation notes

`python -m unittest tests.test_copulas -v` checks independent statsmodels density references, the Student t tail coefficient, all supported family samplers against uniform margins and theoretical Kendall tau, seeded reproducibility, Gaussian/Student t/negative-Frank parameter recovery, failure gates, monotone-margin invariance, complete-case and tie handling, chronological regime shifts, empirical support limits, and JSON-safe analysis output. Negative Frank density is checked against `log(statsmodels.pdf(...))`, because the installed statsmodels negative-Frank `logpdf` returns NaN despite its finite positive PDF.

## References

- [SciPy `rankdata`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.rankdata.html) describes average-rank tie handling.
- [Statsmodels elliptical copulas](https://www.statsmodels.org/stable/_modules/statsmodels/distributions/copula/elliptical.html) and [Archimedean copulas](https://www.statsmodels.org/stable/_modules/statsmodels/distributions/copula/archimedean.html) provide independent density references used by tests.
- [Demarta and McNeil, The t Copula and Related Copulas (2005)](https://doi.org/10.1111/j.1751-5823.2005.tb00254.x) gives the Student t dependence and tail formulation.
