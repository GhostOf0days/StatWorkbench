"""Metadata and catalog construction for core statistical procedures."""
from __future__ import annotations

import copy
import numpy as np

from . import doe, basic_options, basic_model_options


def field(key, label, kind='column', **kw):
    return dict(key=key, label=label, type=kind, required=True, **kw)


def choice(key, label, choices, default):
    return field(key, label, 'select', options=[dict(value=v, label=l) for v, l in choices], default=default)


def number(key, label, default=None, integer=False, **kw):
    if default is not None:
        kw['default'] = default
    return field(key, label, 'integer' if integer else 'number', **kw)


def optional_columns(key, label):
    return dict(key=key, label=label, type='columns', required=False)


def flag(key, label, default=False):
    return field(key, label, 'boolean', default=default)


COLS = field('columns', 'Variables', 'columns')
COL = field('column', 'Variable')
GROUP = field('group', 'Group')
PAIR = [field('x', 'Variable #1'), field('y', 'Variable #2')]
ALT = choice('alternative', 'Alternative hypothesis', [('less', 'Less than'), ('two-sided', 'Not equal'), ('greater', 'Greater than')], 'two-sided')
TYPES = choice('test_type', 'T-test type', [('pooled', 'Equal variances'), ('welch', 'Unequal variances (Welch)'), ('paired', 'Paired')], 'pooled')
CONF = number('confidence', 'Confidence level', .95, min=.01, max=.999, step=.01)
REG = [field('response', 'Dependent variable'), field('predictors', 'Independent variables', 'columns')]
INTERCEPT = flag('intercept', 'Include intercept', True)
MATRIX = choice('matrix', 'Perform PCA on', [('correlation', 'Correlation matrix'), ('covariance', 'Covariance matrix')], 'correlation')
QT = choice('quantile', 'Percentile definition', [(str(i), label) for i, label in enumerate([
    'Inverse EDF (type 1)', 'Averaged EDF (type 2)', 'Nearest order statistic (type 3)',
    'Interpolated EDF (type 4)', 'Midway knots (type 5)', 'Expected order statistics (type 6)',
    'Mode interpolation / Excel (type 7)', 'Median unbiased (type 8)', 'Normal unbiased (type 9)'], 1)], '7')
_B = 'Basic statistics'
_A = 'ANOVA and multivariate'
_D = 'Design of experiments'
_R = 'Regression'
_N = 'Nonparametric statistics'
_ENTRIES = []


def entry(id, name, category, fields, description, limitations=(), coverage='core'):
    _ENTRIES.append(dict(id=str(id), name=name, category=category, fields=fields,
        description=description, coverage=coverage, limitations=list(limitations)))


_DESC_FIELDS = [
    flag('sta.bst.ds.ao.0', 'Plot histogram'),
    flag('sta.bst.ds.ao.1', 'Overlay histogram with normal curve'),
    number('sta.bst.ds.ao.2', 'Number of intervals [NI>2 or 0 for auto]', 0, integer=True, min=0, max=10000),
    choice('sta.percentile.def', 'Percentiles definition', [(str(i), label) for i, label in enumerate([
        '1. Inverse of EDF (SAS-3)', '2. EDF with averaging (SAS-5)',
        '3. Observation closest to N*p (SAS-2)', '4. Interpolation of EDF (SAS-1)',
        '5. Piecewise linear interpolation of EDF (midway values as knots)',
        '6. Interpolation of the expectations for the order statistics (SPSS,NIST)',
        '7. Interpolation of the modes for the order statistics (Excel)',
        '8. Interpolation of the approximate medians for order statistics',
        "9. Blom's unbiased approximation"])], '6'),
    choice('sta.bst.ds.report', 'Report', [('0', 'Separate for each variable (two columns)'), ('1', 'Combined single table'), ('2', 'Separate for each variable (wide)')], '2'),
    choice('vars.ui.sortby', 'Sort variables by', [('0', 'None (original order)'), ('1', 'Names A-Z'), ('2', 'Names Z-A'), ('3', 'Ascending means'), ('4', 'Descending means')], '0'),
    flag('sta.chart.qq', 'Q-Q Plot'), CONF,
]
_DESC_LIMITS = [
    'Automatic histogram boundaries use a Sturges-based width policy. Normal Q-Q charts use Blom plotting positions and fitted-normal quantiles.',
    'The MAD report column uses type-7 interpolation of absolute deviations in source order and is order-sensitive. Conventional median absolute deviation is supplied separately.',
]
entry(1001, 'Descriptive Statistics', _B, [COLS] + _DESC_FIELDS,
      'Three report layouts, moments, quantiles, optional histogram/normal overlay and Q-Q chart.', _DESC_LIMITS)
entry(1002, 'Descriptive Statistics (use group variable)', _B, [COL, GROUP] + [
    dict(f, options=[dict(v, label=v['label'].replace('variable', 'group')) for v in f['options']]) if f['key']=='sta.bst.ds.report' else f for f in _DESC_FIELDS],
      'The same summaries and chart options separately for each nonmissing group.',
      _DESC_LIMITS + ['Missing group labels and missing values are excluded.'])
entry(1004, 'One-Sample z-Test for Mean', _B, [COL, number('mean', 'Hypothesized population mean', 0), number('variance', 'Known population variance', min=0), ALT, CONF],
      'Normal z test with user-supplied population variance.', ['Population variance is required, not estimated from the sample.'])
entry(1007, 'Two-Sample z-Test for Means', _B, PAIR + [number('difference', 'Hypothesized mean difference', 0), number('variance_x', 'Population variance #1', min=0), number('variance_y', 'Population variance #2', min=0), ALT, CONF],
      'Difference-of-means z test for independent samples with known population variances.')
entry(1003, 'One-Sample T-Test', _B, [COLS, number('mean', 'Hypothesized value', 0), ALT, CONF], 'One-sample Student t tests and confidence intervals.')
entry(1005, 'Two-Sample T-Test', _B, PAIR + [TYPES, number('difference', 'Hypothesized mean difference', 0), ALT, CONF], 'Pooled, Welch or paired Student t test.')
entry(10052, 'Two-Sample T-Test (use summarized data)', _B,
      [number('n1', 'Sample size #1', integer=True, min=2), number('mean1', 'Mean #1'), number('sd1', 'Standard deviation #1', min=0),
       number('n2', 'Sample size #2', integer=True, min=2), number('mean2', 'Mean #2'), number('sd2', 'Standard deviation #2', min=0),
       choice('test_type', 'T-test type', [('pooled', 'Equal variances'), ('welch', 'Unequal variances (Welch)')], 'pooled'), number('difference', 'Hypothesized mean difference', 0), ALT, CONF],
      'Pooled or Welch t test calculated from sample summaries.')
entry(10053, 'Two-Sample T-Test (use group variable)', _B, [COL, GROUP,
      choice('test_type', 'T-test type', [('pooled', 'Equal variances'), ('welch', 'Unequal variances (Welch)')], 'pooled'), number('difference', 'Hypothesized mean difference', 0), ALT, CONF],
      'Compare two groups in order of first appearance.', ['Exactly two nonmissing groups are required; no group-code selection control.'])
entry(1008, 'F-Test for Variances', _B, PAIR + [ALT, CONF], 'F ratio and confidence interval for the ratio of two normally distributed population variances.')
entry(1009, 'Linear Correlations [Pearson]', _B, [COLS, ALT], 'Pairwise Pearson correlation coefficients and p-values.', ['Rows are removed per variable pair; no multiplicity adjustment.'])
entry(1010, 'Covariance', _B, [COLS], 'Pairwise sample covariance matrix (N−1 denominator).')
entry(1016, 'Partial Correlations', _B, [COLS, field('controls', 'Covariates (control)', 'columns'),
      choice('missing', 'Missing-value removal', [('casewise', 'Casewise deletion'), ('pairwise', 'Pairwise deletion')], 'pairwise'), ALT],
      'Residual correlation controlling for the selected numeric covariates.')
entry(1011, 'Normality Tests', _B, [COLS], 'Shapiro–Wilk, D’Agostino K², Anderson–Darling, and Lilliefors normality tests.',
      ['Shapiro–Wilk p-values above 5000 observations are approximate; Anderson–Darling reports critical values, not an invented p-value.'])
entry(1012, 'Frequency Tables (categorical data)', _B, [field('columns', 'Categorical variables', 'columns'),
      choice('order', 'Row order', [('count_asc', 'Ascending frequency'), ('count_desc', 'Descending frequency'), ('asc', 'Ascending'), ('desc', 'Descending')], 'asc')], 'Counts, percentages and cumulative percentages for nonmissing categories.')
for aid, name in [('1013', 'Frequency Tables (continuous data)'), ('1015', 'Histogram')]:
    entry(aid, name, _B, [COLS, number('bins', 'Number of bins (0 for automatic)', 0, integer=True, min=0), choice('closed', 'Bin intervals', [('left', 'Left-closed'), ('right', 'Right-closed')], 'left')],
          'Continuous frequency tables and histogram with explicit bin edges.', ['Automatic bins use a Sturges-based 1/2/5 width policy; an open outer boundary extends the range.'])
entry(1014, 'Cross Tabulation and Chi-Square', _B, [field('row', 'Row category'), field('column', 'Column category'), flag('correction', 'Yates correction for 2×2 tables', True)],
      'Observed and expected counts, Pearson chi-square, Cramér V and Fisher exact test for 2×2.', ['One observation per row; weighted frequency variables and original layout options are not supported.'])
entry(1102, 'One-way ANOVA (unstacked)', _A, [COLS, flag('tukey', 'Tukey HSD comparisons', True)], 'Classical fixed-effects one-way ANOVA; columns are independent groups.')
entry(1103, 'One-way ANOVA (use group variable)', _A, [COL, GROUP, flag('tukey', 'Tukey HSD comparisons', True)], 'Classical fixed-effects one-way ANOVA with a group column.')
for aid, name, count in [('1104', 'Two-way ANOVA', 2), ('1105', 'Three-way ANOVA', 3)]:
    entry(aid, name, _A, [field('response', 'Dependent variable'), field('factors', f'Fixed factors (select {count})', 'columns'),
          flag('interactions', 'Include all interactions', True), choice('ss_type', 'Sum of squares', [('2', 'Type II'), ('3', 'Type III (sum contrasts)')], '2')],
          'Fixed-effects factorial ANOVA with optional interactions.', ['Random factors and expected-mean-square denominators are not supported. Type II/III choice is explicit; original default is unverified.'])
entry(1108, 'Repeated Measures (Within Subjects) ANOVA', _A, [field('columns', 'Repeated measurements (one subject per row)', 'columns')],
      'One within-subject factor, complete cases; reports uncorrected and Greenhouse–Geisser results.', ['One within-subject factor only; no Huynh–Feldt or Mauchly test.'])
entry(1106, 'Mixed Treatment by Subjects ANOVA', _A, [GROUP, field('columns', 'Repeated measurements (one subject per row)', 'columns')],
      'Balanced mixed ANOVA: one between-subject group and one within-subject factor.', ['Requires equal group sizes, at least two subjects per cell, and sphericity; missing subjects are removed as complete cases.'])
entry(1107, 'Mixed ANOVA with Two Treatments', _A, [field('factors', 'Between-subject factors (select 2)', 'columns'), field('columns', 'Repeated measurements (one subject per row)', 'columns')],
      'Balanced mixed ANOVA with two fixed between-subject factors and one repeated factor.', ['Requires a fully crossed balanced between-subject design and sphericity; no sphericity correction.'])
entry(1109, 'General Linear Model (GLM)', _A, [field('response', 'Continuous response'), optional_columns('factors', 'Fixed factors'), optional_columns('predictors', 'Numeric covariates'),
      flag('interactions', 'Include factor interactions', False), choice('coding', 'Factor coding', [('Treatment', 'Dummy'), ('Sum', 'Effect'), ('Helmert', 'Orthogonal Helmert')], 'Treatment')],
      'OLS model with categorical fixed factors and continuous covariates.', ['A single response is supported. Random factors and multivariate-response tests are not implemented.'])
# Design-specific error strata are implemented separately from GLM.
_DOE_IDS = frozenset(str(i) for i in range(1201, 1209))
_ENTRIES.extend(doe.catalog())
entry(1110, 'Discriminant Function Analysis', _A, [COLS, GROUP, choice('priors', 'Prior probabilities', [('empirical', 'Proportional to group sizes'), ('equal', 'Same for all groups')], 'empirical'), flag('cross_validate', 'Leave-one-out validation', False)],
      'Linear discriminant analysis with common within-class covariance.', ['In-sample predictions are identified as such. Original variable-selection and classification-rule details are unverified.'])
entry(1120, 'Principal Component Analysis (PCA)', _A, [COLS, MATRIX], 'PCA eigenvalues, component coefficients, loadings, scores and scree plot.')
entry(1121, 'Factor Analysis', _A, [COLS, MATRIX, choice('retention', 'Factor retention', [('count', 'Exactly X factors'), ('eigenvalue', 'Eigenvalue greater than X')], 'eigenvalue'), number('threshold', 'X', 1, min=0),
      choice('rotation', 'Rotation', [('none', 'None'), ('varimax', 'Varimax'), ('quartimax', 'Quartimax'), ('biquartimax', 'Biquartimax'), ('equamax', 'Equamax'), ('orthomax', 'Orthomax')], 'none'), number('gamma', 'Orthomax gamma', 0)],
      'Principal-component factor extraction with optional orthomax rotations.', ['Other extraction methods are unsupported. Rotation uses unnormalized loadings; equamax gamma is retained-factor count / 2.'])
entry(1130, 'K-Means Clustering', _A, [COLS, number('clusters', 'Number of clusters', 2, integer=True, min=1), number('max_iter', 'Maximum iterations', 10, integer=True, min=1, max=1000), flag('standardize', 'Standardize variables', False), number('seed', 'Random seed', 0, integer=True)],
      'K-means++ initialization, ten restarts and Lloyd optimization.', ['Initialization uses seeded k-means++ with ten restarts and Lloyd optimization.'])
entry(1132, 'Hierarchical Clustering', _A, [COLS, choice('cluster_axis', 'Cluster', [('rows', 'Cases (rows)'), ('columns', 'Variables (columns)')], 'rows'),
      choice('linkage', 'Linkage method', [(x, x.title()) for x in ['single', 'complete', 'average', 'weighted', 'centroid', 'median', 'ward']], 'average'),
      choice('metric', 'Distance', [('euclidean', 'Euclidean'), ('sqeuclidean', 'Squared Euclidean'), ('chebyshev', 'Chebychev'), ('cityblock', 'Manhattan'), ('minkowski', 'Minkowski'), ('cosine', 'Cosine distance')], 'sqeuclidean'),
      number('power', 'Minkowski power', 2, min=1), number('clusters', 'Number of clusters', 2, integer=True, min=1)],
      'Agglomerative clustering with a linkage table and exact requested cluster count.', ['Flexible linkage, generalized/angle distances and graphical dendrogram are not implemented. Ward, centroid and median require Euclidean distance.'])
entry(1301, 'Multiple Linear Regression', _R, REG + [INTERCEPT, CONF], 'OLS coefficients, inference, fitted values, residual diagnostics and R².')
entry(1302, 'Weighted Least Squares Regression', _R, REG + [field('weights', 'Positive inverse-variance weights'), INTERCEPT, CONF], 'WLS using weights proportional to inverse observation variance.', ['Weight semantics are explicit; regression uncertainty assumes supplied variance weights are appropriate.'])
entry(1303, 'Polynomial Regression', _R, [field('response', 'Dependent variable'), field('predictor', 'Independent variable'), number('degree', 'Polynomial degree', 2, integer=True, min=1, max=10), INTERCEPT, CONF], 'OLS regression on raw powers of one predictor.', ['High-degree fits can be ill-conditioned; singular designs are rejected.'])
entry(1310, 'Curve Fit', _R, [field('response', 'Dependent variable'), field('predictor', 'Independent variable'), choice('model', 'Model', [('linear', 'Linear'), ('quadratic', 'Quadratic'), ('cubic', 'Cubic'), ('inverse', 'Inverse'), ('logarithmic', 'Logarithmic'), ('power', 'Power'), ('exponential', 'Exponential'), ('growth', 'Growth'), ('compound', 'Compound'), ('sigmoid', 'S-curve')], 'linear')],
      'Fit one named curve by ordinary or transformed least squares.', ['Logistic bounded curve and multi-model comparison are not implemented. Power/exponential/growth/compound/S-curve fit log(y); no retransformation bias correction.'])
entry(1304, 'Forward Stepwise', _R, REG + [number('alpha', 'Enter if alpha <', .05, min=.0001, max=.999), CONF], 'Forward predictor selection by partial t-test p-values.', ['Unadjusted post-selection inference is exploratory; no validation-set performance estimate.'])
entry(1305, 'Backward Stepwise', _R, REG + [number('alpha', 'Remove if alpha >', .10, min=.0001, max=.999), CONF], 'Backward elimination by partial t-test p-values.', ['Unadjusted post-selection inference is exploratory; no validation-set performance estimate.'])
entry(1307, 'Best Subsets Regression', _R, REG + [choice('criterion', 'Select model by', [('bic', 'BIC'), ('aic', 'AIC'), ('adj_r2', 'Adjusted R²')], 'bic'), CONF], 'Exact maximum-R² model for every predictor count using streamed QR search and safe residual bounds.', ['Search has exponential worst-case runtime; interrupted searches produce no partial result. Includes an additional overall criterion-selected model and the intercept-only model; this overall selection criterion is an explicit extension.'])
entry(1306, 'Binary Logistic', _R, REG + [CONF], 'Binomial logit maximum likelihood, odds ratios and predicted probabilities.', ['Response must be 0 or 1; no automatic category recoding. Separation and nonconvergence are rejected.'])
entry(1320, 'Heteroscedasticity Tests', _R,
      [field('residuals', 'Residuals'), field('predictors', 'Independent variables', 'columns'),
       flag('sta.reg.modelsum.opt', 'Display model summary for each test'),
       flag('reg.bpg', 'Breusch-Pagan-Godfrey (BPG) test', True),
       flag('reg.harvey', 'Harvey test', True), flag('reg.glejser', 'Glejser test', True),
       flag('reg.arch', "Engle's ARCH test", True),
       number('sta.time.lags_c', 'Lags count', 1, integer=True, min=1),
       flag('reg.white', 'White test', True),
       choice('sta.time.reg.include', 'Include terms', [('0', 'All cross-terms'), ('1', 'Linear and squared terms'), ('2', 'Only squared terms')], '0')],
      'Auxiliary regressions operate directly on supplied residuals, preserving their row order.',
      ['The BPG statistic is N × R² of the scaled squared-residual regression.',
       'Missing internal observations are rejected; only entirely empty trailing rows are trimmed. Singular auxiliary models or undefined transforms produce unavailable tests.'])
entry(1403, 'Rank and Percentile', _N, [COLS, choice('ties', 'Ties assigned to', [('average', 'Average rank'), ('max', 'Maximum rank'), ('min', 'Minimum rank'), ('ordinal', 'Sequential ranks')], 'average')],
      'Ascending and descending ranks with percentile fractions (rank − 1)/(N − 1).', ['Percentiles are stored as fractions and formatted as percentages; ordinal ties retain source order for ascending ranks.'])
entry(1404, 'Rank Correlations [Spearman R, Kendall Tau, Gamma]', _N, [COLS, ALT], 'Spearman ρ, Kendall τ-b and Goodman–Kruskal γ.', ['Gamma is descriptive only: no unsupported p-value is reported. No multiplicity adjustment.'])
entry(1405, 'Fechner Correlation', _N, [COLS], 'Mean-deviation sign concordance: 2 × matching signs / N − 1.', ['Zero deviations are retained: two zero signs match, while one zero sign does not; no significance test.'])
entry(1401, '2x2 Contingency Table Analysis (tabulated data)', _N, [COLS, flag('correction', 'Yates correction', True)], 'Analyze a 2×2 matrix of counts, including Fisher exact test.', ['Exactly two numeric count columns and two rows; integer counts only.'])
entry(1411, 'NxK Contingency Table Analysis (tabulated data)', _N, [COLS, flag('correction', 'Yates correction for 2×2', True)], 'Pearson chi-square for a tabulated matrix of integer counts.', ['No rounding or truncation is performed; use integer nonnegative counts.'])
entry(1406, 'Two Independent Samples [Mann-Whitney, Runs Test]', _N, PAIR + [ALT], 'Mann–Whitney U, two-sample runs inference, Kolmogorov–Smirnov and Rosenbaum tests.', ['Tied runs use two deterministic orderings; exact permutation tails are unconditional on pooled ties. The normal two-tail runs convention is used.'])
entry(14063, 'Two Independent Samples (use group variable)', _N, [COL, GROUP, ALT], 'Two independent samples from two group labels.', ['Exactly two groups in order of first appearance. Runs test omitted for ties.'])
entry(1407, 'Multiple Independent Samples [Kruskal-Wallis, Median Test]', _N, [COLS], 'Kruskal–Wallis and Mood median tests for independent columns.')
entry(14072, 'Multiple Independent Samples (use group variable)', _N, [COL, GROUP], 'Kruskal–Wallis and Mood median tests for groups.')
entry(1408, 'Two Related Samples [Wilcoxon Pairs, Sign Test]', _N, PAIR + [ALT], 'Wilcoxon signed-rank and exact binomial sign tests on paired differences.', ['Zero differences excluded; Wilcoxon uses SciPy automatic exact/asymptotic selection.'])
entry(1409, 'Multiple Related Samples [Friedman ANOVA, Concordance]', _N, [field('columns', 'Repeated measurements', 'columns')], 'Friedman chi-square and Kendall W for at least three related measurements.')
entry(14092, 'Multiple Related Samples (use group variable)', _N, [COL, GROUP, {**field('subject', 'Subject identifier (optional)'), 'required':False}],
      'Friedman and Kendall W from long-format related measurements.', ['Without a subject identifier, observations are paired by their position within each group; this convention is stated in results. Explicit identifiers remain available.'])
entry(1410, "Cochran's Q Test", _N, [field('columns', 'Related binary measurements', 'columns')], 'Cochran Q test for at least three paired binary responses.')


basic_options.extend_catalog(_ENTRIES)
basic_model_options.extend_catalog(_ENTRIES)
# Additional documented procedures use explicit API defaults instead of
# undocumented command identifiers.
for _entry in _ENTRIES:
    if _entry['id']=='1004':
        for _field in _entry['fields']:
            if _field['key']=='column':_field['required']=False
        _entry['fields'].extend([
            choice('help.z.input_mode','Input form (documented help capability)', [('raw','Raw observations'),('summary','Summarized mean and sample size')],'raw'),
            dict(key='help.z.n',label='Summarized sample size',type='integer',required=False,min=2),
            dict(key='help.z.sample_mean',label='Summarized sample mean',type='number',required=False)])
    if _entry['id']=='1306':
        _entry['fields'].append(optional_columns('help.logit.categorical','Categorical predictors (last sorted category is reference)'))
        _entry['limitations'].append('Categorical predictors use treatment indicators with the last sorted category as the reference.')
    if _entry['id']=='1008':
        _entry['fields'].append(number('help.f.ratio','Hypothesized variance ratio (documented help capability)',1,min=np.finfo(float).tiny))


def catalog():
    return copy.deepcopy(_ENTRIES)


_META = {x['id']: x for x in _ENTRIES}
