"""Latin-square and related design-of-experiments analyses."""
from __future__ import annotations

import copy
import math
import numpy as np
import pandas as pd
from scipy.stats import f as f_distribution
from backend.common import validate_dataset

_NAMES = {
    '1201': '1: Three Factors (A, B, C) With No Interactions',
    '1202': '2: Four Factors (A, B, C, D) With Partial Interactions',
    '1203': '3: Four Factors (A, B, C, D) With Partial Confounding Of AxBxC Interaction',
    '1204': '4: Greco-Latin With No Interactions',
    '1205': '5: Repeated Measures Latin Square (Random Assignment Of Groups To Rows)',
    '1206': '6: Fractional Replication Of A Three-Factor Factorial Experiment In Incomplete Blocks',
    '1207': '7: Plan 5 With Superimposing An Orthogonal Latin Square',
    '1208': '8: AxBxC (Same Squares Used For All Levels Of Factor C)',
}
_ROLES = {
    '1201': ['a', 'b', 'c'], '1202': ['a', 'b', 'c', 'd'],
    '1203': ['a', 'b', 'c', 'd'], '1204': ['a', 'b', 'c', 'd'],
    '1205': ['a', 'b', 'subject', 'group'],
    '1206': ['a', 'b', 'subject', 'group'],
    '1207': ['a', 'b', 'c', 'subject', 'group'],
    '1208': ['a', 'b', 'c', 'subject', 'group'],
}
_COMMON_LIMITS = [
    'Responses are truncated toward zero before analysis; fractional inputs produce a warning.',
    'Factors and identifiers require contiguous positive integer codes starting at 1. Complete balanced designs are required; missing or malformed observations are rejected.',
    'ANOVA terms and error strata follow the design-specific model; validate assumptions against the study design.',
]


def catalog():
    entries = []
    for aid, name in _NAMES.items():
        fields = [dict(key='response', label='Variable', type='column', required=True)]
        for role in _ROLES[aid]:
            label = ('Group' if role == 'group' else 'Subject' if role == 'subject'
                     else 'Factor ' + role.upper())
            help_text = None
            if role == 'subject' and aid in ('1205', '1206', '1207'):
                label = 'Factor ' + ('D' if aid == '1207' else 'C')
                help_text = 'This field is used as subject ID (1..cases per cell), reused within each group.'
            fields.append(dict(key=role, label=label, type='column', required=True,
                               **({'help': help_text} if help_text else {})))
        fields.append(dict(key='cases_per_cell', label='Number of Cases per Cell',
                           type='integer', required=True, min=1, max=10000,
                           help='Replicates per design cell; for repeated designs, subjects per group.'))
        limits = list(_COMMON_LIMITS)
        if aid == '1208':
            limits.append('Plan 8 currently requires the number of C levels to equal square order. The native group-to-row indexing for unequal dimensions is unresolved. Subject IDs must be unique across groups, and group codes are contiguous blocks by C.')
        entries.append(dict(id=aid, name=name, category='Design of experiments',
                            fields=fields, coverage='core',
                            description='Latin-square ANOVA, allocation, marginal means and sums, with design-specific error strata.',
                            limitations=limits))
    return copy.deepcopy(entries)


def _input(aid, data, options):
    data = validate_dataset(data)
    o = dict(options)
    if aid in ('1201', '1204') and 'factors' in o:
        factors = o['factors']
        if not isinstance(factors, list) or len(factors) != len(_ROLES[aid]):
            raise ValueError('Select the required number of Latin-square factors.')
        for key, name in zip(_ROLES[aid], factors):
            o.setdefault(key, name)
    names = ['response'] + _ROLES[aid]
    selected = [o.get(key) for key in names]
    if any(name not in data['columns'] for name in selected):
        raise ValueError('Select a valid response and every required design factor.')
    if len(set(selected)) != len(selected):
        raise ValueError('Response, factor, group and subject roles must use distinct columns.')
    if not data['rows']:
        raise ValueError('The design contains no observations.')
    frame = pd.DataFrame(data['rows'], columns=data['columns'])[selected]
    frame.columns = names
    try:
        frame = frame.apply(pd.to_numeric, errors='raise').astype(float)
    except (ValueError, TypeError):
        raise ValueError('All design columns must contain numeric data.') from None
    if not np.isfinite(frame.to_numpy()).all():
        raise ValueError('Missing and nonfinite values are not allowed in a balanced design.')
    levels = {}
    for key in _ROLES[aid]:
        values = frame[key].to_numpy()
        if np.any(values < 1) or np.any(values != np.trunc(values)) or np.any(values > len(frame)):
            raise ValueError(f'{key}: factor and subject codes must be positive integers starting at 1.')
        unique = np.unique(values)
        if not np.array_equal(unique, np.arange(1, len(unique)+1)):
            raise ValueError(f'{key}: factor and subject codes must be contiguous integers starting at 1.')
        levels[key] = len(unique)
        frame[key] = values.astype(np.int64)
    values = frame['response'].to_numpy()
    if np.any(np.abs(values) >= 2**53):
        raise ValueError('Response magnitudes must be below 2^53 for reliable integer arithmetic.')
    truncated = np.trunc(values)
    warnings = []
    if np.any(values != truncated):
        warnings.append('Responses were truncated toward zero. Fractional response information was discarded.')
    frame['response'] = truncated
    # Center after native-compatible conversion to avoid cancellation in sums of squares.
    frame['z'] = truncated - truncated.mean()
    n = o.get('cases_per_cell', o.get('sta.latsq.cases_pc'))
    if isinstance(n, bool):
        raise ValueError('Number of cases per cell must be an integer from 1 to 10000, not a boolean.')
    if n is None and aid in ('1201', '1204'):
        counts = frame.groupby(['a', 'b']).size()
        if counts.nunique() == 1:
            n = int(counts.iloc[0])
    try:
        numeric = float(n)
        n = int(numeric)
    except (ValueError, TypeError, OverflowError):
        raise ValueError('Number of cases per cell must be an integer from 1 to 10000.') from None
    if not math.isfinite(numeric) or numeric != n or not 1 <= n <= 10000:
        raise ValueError('Number of cases per cell must be an integer from 1 to 10000.')
    return frame, levels, n, warnings


def _balanced(frame, keys, cells, count, message):
    sizes = frame.groupby(keys, sort=False).size()
    if len(sizes) != cells or not np.all(sizes.to_numpy() == count):
        raise ValueError(message)


def _latin(frame, row, column, treatment, p, block=None):
    keys = ([block] if block else []) + [row, column]
    allocation = frame[keys + [treatment]].drop_duplicates()
    blocks = frame[block].nunique() if block else 1
    if len(allocation) != blocks*p*p:
        raise ValueError('Each square cell must contain one treatment level.')
    for first, second in ((row, column), (row, treatment), (column, treatment)):
        _balanced(allocation, ([block] if block else []) + [first, second], blocks*p*p, 1,
                  'A valid Latin square is required: every treatment occurs once in each row and column.')


def _validate(aid, frame, levels, n):
    p = levels['a']
    if p < 2 or levels['b'] != p:
        raise ValueError('A and B must have the same number of levels, at least two.')
    if aid in ('1201', '1202', '1203', '1204'):
        if levels['c'] != p:
            raise ValueError('A, B and C must have equal numbers of levels.')
        if aid in ('1201', '1204'):
            _balanced(frame, ['a', 'b'], p*p, n, 'Every square cell must have the specified number of cases.')
            _latin(frame, 'a', 'b', 'c', p)
            if aid == '1204':
                if levels['d'] != p or p < 3:
                    raise ValueError('A Graeco-Latin square requires equal orders of at least three.')
                _latin(frame, 'a', 'b', 'd', p)
                allocation = frame[['a', 'b', 'c', 'd']].drop_duplicates()
                _balanced(allocation, ['c', 'd'], p*p, 1, 'Latin and Greek squares must be orthogonal.')
        else:
            d = levels['d']
            if d < 2 or (aid == '1203' and d != p):
                raise ValueError('Plan 2 requires at least two D blocks; Plan 3 requires D to have square order levels.')
            _balanced(frame, ['a', 'b', 'd'], p*p*d, n, 'Each A×B×D cell must have the specified number of cases.')
            _latin(frame, 'a', 'b', 'c', p, 'd')
            if aid == '1203':
                _balanced(frame, ['a', 'b', 'c'], p**3, n,
                          'Plan 3 requires each A×B×C cell once across the D block allocations, with equal replication.')
    else:
        groups = levels['group']
        c = levels.get('c', 1)
        expected_groups = p*c if aid == '1208' else p
        if groups != expected_groups:
            raise ValueError('Group count does not match the design allocation.')
        if aid == '1208' and c != p:
            raise ValueError('Plan 8 with unequal C levels and square order is not yet verified; equal dimensions are required.')
        _balanced(frame, ['group', 'a'], groups*p, n, 'Each group×A cell must contain exactly the specified number of subjects.')
        _balanced(frame, ['group', 'subject'], groups*n, p, 'Every subject must be observed once at each A level in its group.')
        _balanced(frame, ['group', 'subject', 'a'], groups*n*p, 1, 'A subject has duplicate or missing repeated measurements.')
        if aid == '1208':
            if levels['subject'] != groups*n or frame.groupby('subject')['group'].nunique().max() != 1:
                raise ValueError('Plan 8 subject IDs must be unique across groups, contiguous from 1.')
            if not np.all(frame['c'].to_numpy() == (frame['group'].to_numpy()-1)//p + 1):
                raise ValueError('Plan 8 groups must be coded in consecutive blocks of square order for each C level.')
            frame['row'] = (frame['group']-1) % p + 1
            _latin(frame, 'row', 'a', 'b', p, 'c')
            if len(frame[['row', 'a', 'b']].drop_duplicates()) != p*p:
                raise ValueError('Plan 8 requires the same Latin square at all C levels.')
        else:
            if levels['subject'] != n:
                raise ValueError('Subject IDs must be 1..cases per cell, reused within each group.')
            _latin(frame, 'group', 'a', 'b', p)
            if aid == '1207':
                if c != p or p < 3:
                    raise ValueError('Plan 7 requires an orthogonal square of the same order, at least three.')
                _latin(frame, 'group', 'a', 'c', p)
                allocation = frame[['group', 'a', 'b', 'c']].drop_duplicates()
                _balanced(allocation, ['b', 'c'], p*p, 1, 'The superimposed B and C squares must be orthogonal.')
    return p


class _Squares:
    def __init__(self, frame):
        self.frame = frame
        self.total = float(np.dot(frame.z, frame.z))
        self.tol = max(self.total, 1)*1e-11
        self.components = {}

    def q(self, keys, denominator):
        totals = self.frame.groupby(keys, sort=False).z.sum().to_numpy()
        return float(np.dot(totals, totals) / denominator)

    def within(self, keys):
        residual = self.frame.z - self.frame.groupby(keys).z.transform('mean')
        return float(np.dot(residual, residual))

    def repeated_errors(self):
        group_mean = self.frame.groupby('group').z.transform('mean')
        subject_mean = self.frame.groupby(['group', 'subject']).z.transform('mean')
        cell_mean = self.frame.groupby(['group', 'a']).z.transform('mean')
        subject_residual = subject_mean - group_mean
        residual = self.frame.z - subject_mean - cell_mean + group_mean
        return float(np.dot(subject_residual, subject_residual)), float(np.dot(residual, residual))

    def add(self, name, ss, df, denominator=None, aggregate=False):
        if ss < -self.tol:
            raise ValueError(f'Allocation produced negative {name} sum of squares; the design is not valid for this plan.')
        if ss < 0 or (df == 0 and abs(ss) <= self.tol):
            ss = 0.0
        if df < 0 or (df == 0 and ss > self.tol):
            raise ValueError(f'Allocation is inconsistent with the {name} degrees of freedom.')
        self.components[name] = (ss, int(df), denominator, aggregate)
        return ss

    def table(self, warnings):
        rows = []
        for name, (ss, df, denominator, aggregate) in self.components.items():
            ms = ss / df if df and not aggregate else None
            f_stat = probability = None
            if denominator and df > 0:
                err, edf, _, _ = self.components[denominator]
                if edf > 0 and err > 0:
                    f_stat = ms / (err/edf)
                    probability = float(f_distribution.sf(f_stat, df, edf))
                else:
                    warning = f'{denominator} has no positive estimable error variance; its F tests are unavailable.'
                    if warning not in warnings:
                        warnings.append(warning)
            rows.append([name, ss, df, ms, f_stat, probability])
        return dict(title='Analysis of Variance', columns=['Source', 'SS', 'DF', 'MS', 'F', 'Prob. > F'], rows=rows)


def _between_plan(aid, s, p, n, levels):
    q = s.q
    if aid in ('1201', '1204'):
        roles = ['a', 'b', 'c'] + (['d'] if aid == '1204' else [])
        mains = [s.add('Factor '+key.upper(), q([key], p*n), p-1, 'Within') for key in roles]
        cells = q(['a', 'b'], n)
        s.add('Residual', cells-sum(mains), (p-1)*(p+1-len(roles)), 'Within')
        s.add('Within', s.within(['a', 'b']), p*p*(n-1))
    elif aid == '1202':
        d = levels['d']
        mains = {key: s.add('Factor '+key.upper(), q([key], p*d*n), p-1, 'Within') for key in ['a', 'b', 'c']}
        dss = s.add('Factor D', q(['d'], p*p*n), d-1, 'Within')
        cross = [s.add(key.upper()+' × D', q([key, 'd'], p*n)-mains[key]-dss,
                       (p-1)*(d-1), 'Within') for key in ['a', 'b', 'c']]
        cells = q(['a', 'b', 'd'], n)
        s.add('Residual', cells-sum(mains.values())-dss-sum(cross), d*(p-1)*(p-2), 'Within')
        s.add('Within', s.within(['a', 'b', 'd']), d*p*p*(n-1))
    else:
        mains = {key: s.add('Factor '+key.upper(), q([key], p*p*n), p-1, 'Within') for key in 'abcd'}
        cross = {}
        for left, right in [('a', 'b'), ('a', 'c'), ('b', 'c')]:
            cross[left+right] = s.add(left.upper()+' × '+right.upper(),
                q([left, right], p*n)-mains[left]-mains[right], (p-1)**2, 'Within')
        cells = q(['a', 'b', 'c'], n)
        s.add('A × B × C (partial)', cells-sum(mains.values())-sum(cross.values()),
              (p-1)**3-(p-1), 'Within')
        s.add('Within', s.within(['a', 'b', 'c']), p**3*(n-1))
    s.add('Total', s.total, len(s.frame)-1, aggregate=True)


def _repeated_plan(aid, s, p, n, levels):
    q = s.q
    extended = aid == '1208'
    c = levels['c'] if extended else 1
    groups = p*c
    subjects = q(['subject'] if extended else ['group', 'subject'], p)
    group_ss = q(['group'], p*n)
    subject_error, within_error = s.repeated_errors()
    s.add('Between subjects', subjects, groups*n-1, aggregate=True)
    if extended:
        css = s.add('Factor C', q(['c'], p*p*n), c-1, 'Subjects within groups')
        row_ss = s.add('Rows', q(['row'], c*p*n), p-1, 'Subjects within groups')
        cr = s.add('C × Rows', group_ss-css-row_ss, (c-1)*(p-1), 'Subjects within groups')
    else:
        s.add('Factor C' if aid == '1206' else 'Groups', group_ss, p-1, 'Subjects within groups')
    s.add('Subjects within groups', subject_error, groups*(n-1))
    s.add('Within subjects', s.total-subjects, groups*n*(p-1), aggregate=True)
    ass = s.add('Factor A', q(['a'], c*p*n), p-1, 'Error within')
    bss = s.add('Factor B', q(['b'], c*p*n), p-1, 'Error within')
    if extended:
        qab, qac, qbc, qabc = q(['a', 'b'], n*c), q(['a', 'c'], n*p), q(['b', 'c'], n*p), q(['a', 'b', 'c'], n)
        s.add('A × C', qac-ass-css, (p-1)*(c-1), 'Error within')
        s.add('B × C', qbc-bss-css, (p-1)*(c-1), 'Error within')
        s.add('A × B prime', qab-ass-bss-row_ss, (p-1)*(p-2), 'Error within')
        s.add('A × B × C prime', qabc-qab-qac-qbc+ass+bss+css-cr,
              (c-1)*(p-1)*(p-2), 'Error within')
    else:
        cell_ss = q(['group', 'a'], n)
        remainder = cell_ss-ass-bss-group_ss
        if aid == '1207':
            cmain = s.add('Factor C', q(['c'], p*n), p-1, 'Error within')
            s.add('Residual', remainder-cmain, (p-1)*(p-3), 'Error within')
        else:
            s.add('A × B (partial)' if aid == '1205' else 'Residual', remainder, (p-1)*(p-2), 'Error within')
    s.add('Error within', within_error, c*p*(p-1)*(n-1))
    s.add('Total', s.total, len(s.frame)-1, aggregate=True)


def _matrix(frame, row, column, title, *, means=False, subset=None):
    f = frame if subset is None else frame.loc[subset]
    table = f.pivot_table(index=row, columns=column, values='response',
                          aggfunc='mean' if means else 'sum', sort=True)
    grouped = f.groupby(row)['response']
    totals = grouped.mean() if means else grouped.sum()
    bottom = f.groupby(column)['response'].mean() if means else f.groupby(column)['response'].sum()
    rows = [[int(i)] + [float(x) for x in values] + [float(totals.loc[i])]
            for i, values in table.iterrows()]
    rows.append(['Total'] + [float(bottom.loc[col]) for col in table.columns] +
                [float(f.response.mean() if means else f.response.sum())])
    return dict(title=title, columns=[row.title()] + [str(x) for x in table.columns] + ['Total'], rows=rows)


def _reports(aid, frame):
    reports = []
    if aid in ('1201', '1202', '1203', '1204'):
        blocks = frame.groupby('d', sort=True) if aid in ('1202', '1203') else [(None, frame)]
        for block, f in blocks:
            suffix = f' — Block {block}' if block is not None else ''
            columns = ['a', 'b', 'c'] + (['d'] if aid == '1204' else [])
            layout = f[columns].drop_duplicates().sort_values(['a', 'b'])
            reports.append(dict(title='Experimental Design'+suffix,
                                columns=[key.upper() for key in columns], rows=layout.values.tolist()))
            reports.append(_matrix(f, 'a', 'b', 'Cell Means and Totals'+suffix, means=True))
    else:
        roles = ['a', 'b'] + (['c'] if aid in ('1207', '1208') else [])
        for role in roles:
            reports.append(_matrix(frame, 'group', role, f'Groups (rows) × {role.upper()} (columns): Sums'))
        # A sparse subject-total table avoids a quadratic matrix when IDs are global.
        subject_totals = frame.groupby(['group', 'subject'], sort=True).response.sum()
        reports.append(dict(title='Groups × Subjects: Sums', columns=['Group', 'Subject', 'Sum'],
                            rows=[[int(g), int(sub), float(v)] for (g, sub), v in subject_totals.items()]))
        layout = frame[['group'] + roles].drop_duplicates().sort_values(['group', 'a'])
        reports.append(dict(title='Experimental Design', columns=['Group']+[x.upper() for x in roles], rows=layout.values.tolist()))
        reports.append(_matrix(frame, 'group', 'a', 'Cell Means and Totals', means=True))
    rows = []
    for role in _ROLES[aid]:
        if role == 'subject':
            continue
        for level, values in frame.groupby(role, sort=True):
            rows.append([role.upper(), int(level), len(values), float(values.response.sum()), float(values.response.mean())])
    reports.append(dict(title='Marginal Means and Totals', columns=['Factor', 'Level', 'N', 'Sum', 'Mean'], rows=rows))
    return reports


def analyze(analysis_id, data, options):
    aid = str(analysis_id)
    if aid not in _NAMES:
        raise ValueError('Unknown Latin-square design.')
    frame, levels, n, warnings = _input(aid, data, options)
    p = _validate(aid, frame, levels, n)
    s = _Squares(frame)
    if aid in ('1201', '1202', '1203', '1204'):
        _between_plan(aid, s, p, n, levels)
        notes = ['Main effects, interactions and residual use the separate Within mean square as the F denominator.']
    else:
        _repeated_plan(aid, s, p, n, levels)
        notes = ['Between-subject effects use Subjects within groups as the F denominator; within-subject effects use Error within.',
                 'The repeated observations of each subject must represent a complete A-level sequence.']
    notes += [f'Square order {p}; cases per cell {n}; {len(frame)} observations.',
              'The Cell Means and Totals report labels marginal means as Total; these margins are averages, not sums.',
              'ANOVA and allocation follow the documented design structure and formulas.']
    return dict(analysis=aid, title=_NAMES[aid], tables=[s.table(warnings)] + _reports(aid, frame),
                charts=[], notes=notes, warnings=warnings)
