"""Application-wide analysis preferences, applied before procedure dispatch."""
from __future__ import annotations

import secrets
from backend.common import MAX_CELLS, MAX_COLUMNS


INDEPENDENT_FIELDS = frozenset(('initial_centers', 'sta.time.wma.weightsvar', 'sta.bst.freq.bins_var'))


def _missing(value):
    return value is None or (isinstance(value, str) and not value.strip())


def observation_field(entry, key, options):
    """Separate observation columns from auxiliary vectors and inactive roles."""
    if key in INDEPENDENT_FIELDS or key == 'sta.in.caselabels':
        return False
    identifier = str(entry.get('id', ''))
    if identifier == '1004' and options.get('help.z.input_mode') == 'summary':
        return False
    if identifier in ('4102', '4103') and key == 'sta.cc.xbar.GROUPS':
        return str(options.get('sta.cc.datalayout', '0' if options.get(key) else '3')) == '0'
    return True


def _filter_observations(data, options, retained, independent, aligned):
    """Compact observations without treating auxiliary-vector rows as cases."""
    columns = list(data['columns'])
    vectors = {name: [row[index] for row in retained]
               for index, name in enumerate(columns)}
    auxiliary_names = {}
    for key, names in independent.items():
        for source in names:
            if source not in auxiliary_names:
                target = source
                if source in aligned:
                    # One worksheet column may be selected in both roles. A
                    # separate name lets each role keep its own row alignment.
                    suffix = 1
                    target = f'__casewise_aux_{suffix}'
                    while target in vectors:
                        suffix += 1
                        target = f'__casewise_aux_{suffix}'
                    columns.append(target)
                index = data['columns'].index(source)
                values = [row[index] for row in data['rows']]
                while values and _missing(values[-1]):
                    values.pop()
                vectors[target] = values
                auxiliary_names[source] = target
        original = options[key]
        if isinstance(original, list):
            options[key] = [auxiliary_names.get(name, name) if isinstance(name, str) else name for name in original]
        else:
            options[key] = auxiliary_names[original]
    length = max((len(values) for values in vectors.values()), default=0)
    if len(columns) > MAX_COLUMNS or length * len(columns) > MAX_CELLS:
        raise ValueError('Independent auxiliary inputs exceed dataset limits after casewise deletion; select fewer input columns.')
    rows = [[vectors[name][row] if row < len(vectors[name]) else None for name in columns]
            for row in range(length)]
    return {**data, 'columns': columns, 'rows': rows}


def apply_preferences(data, options, entry):
    """Casewise deletion uses selected inputs, never unrelated worksheet cells."""
    options = dict(options)
    mode = options.get('missingValues', 'automatic')
    if mode not in ('automatic', 'casewise'):
        raise ValueError('Missing-value preference must be automatic or casewise.')
    seed = options.get('randomSeed')
    if seed is not None:
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2**32-1:
            raise ValueError('Global random seed must be an integer from 0 through 4294967295.')
        if 'seed' not in options:
            options['seed'] = seed or secrets.randbits(32)
    deleted = 0
    if mode == 'casewise':
        options['missing'] = 'casewise'
        selected = set()
        aligned = set()
        independent = {}
        for field in entry.get('fields', []):
            if field.get('type') not in ('column', 'columns'):
                continue
            value = options.get(field['key'])
            values = value if isinstance(value, list) else [value]
            names = [v for v in values if isinstance(v, str) and v in data['columns']]
            if field['key'] in INDEPENDENT_FIELDS:
                if names:
                    independent[field['key']] = names
                continue
            aligned.update(names)
            if observation_field(entry, field['key'], options):
                selected.update(names)
        # Legacy API aliases remain supported by the procedure normalizers.
        for key in ('columns','factors','responses','predictors','random_factors'):
            value = options.get(key, [])
            if isinstance(value, list):
                selected.update(v for v in value if isinstance(v, str) and v in data['columns'])
        aligned.update(selected)
        indices = [i for i, name in enumerate(data['columns']) if name in selected]
        rows = [row for row in data['rows'] if all(not _missing(row[i]) for i in indices)]
        deleted = len(data['rows']) - len(rows)
        data = (_filter_observations(data, options, rows, independent, aligned)
                if deleted and independent else {**data, 'rows': rows})
    return data, options, deleted
