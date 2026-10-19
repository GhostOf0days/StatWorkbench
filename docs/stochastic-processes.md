# Markov-chain and stochastic-process workflow

## Markov Chain & Ergodicity

Select one categorical state column and a transition step. The worksheet row order is treated as equally spaced time; at step `s`, the procedure counts pairs `(state[t], state[t+s])`. Blank endpoints omit that pair. The output includes transition counts, row-normalized empirical probabilities, observed communicating classes, empirical absorbing states, class periods, class closure, and chain-level diagnostics.

Stationary probabilities are calculated only when every empirical probability row is defined and the observed graph has exactly one closed communicating class. If the chain is reducible with one closed class, transient states receive stationary probability zero. With multiple closed classes, the stationary distribution is not unique without an initial-class weighting assumption. Periodicity does not prevent a unique stationary distribution, but it can prevent convergence to that distribution from every starting state.

For a finite chain, irreducibility plus aperiodicity is the usual ergodicity condition; in an irreducible finite chain, the stationary distribution is unique, and aperiodicity determines convergence from arbitrary starting states. Here these are diagnostics of the graph observed in the sample. An unseen transition is not proof that a transition is impossible, and this tool does not test whether the source data satisfy the first-order Markov property. See [MIT's stochastic-process course notes](https://mitocw.ups.edu.ec/courses/mathematics/18-445-introduction-to-stochastic-processes-spring-2015/lecture-notes/) and [CMU's stationary-distribution notes](https://www.math.cmu.edu/~gautam/c/2025-326/notes/markov2-stationary.html).

The current implementation caps the state space at 50 observed states and transition step at 1,000 rows. It is intended for categorical, finite-state sequences; continuous observations need a justified discretization before this analysis. Time-series workflows remain available separately for numeric series, including autocorrelation, stationarity tests, differencing, smoothing, decomposition, and forecasting.

## Validation

The numerical checks cover a known ergodic two-state chain, deterministic period-2 alternation, reducible graphs, unique and non-unique stationary distributions, missing endpoints, state-label collisions, invalid options, and strict worker JSON output. Run them with:

```sh
PYTHONPATH=. .venv/bin/python -m unittest tests.test_stochastic -v
```
