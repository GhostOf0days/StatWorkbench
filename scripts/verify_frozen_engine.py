"""Compare representative analyses through source and frozen NDJSON workers."""
from pathlib import Path
import json
import math
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
data = {'name': 'Frozen verification', 'columns': ['x', 'y', 'status'],
        'rows': [[1, 2, 1], [2, 4, 0], [3, 5, 1], [5, 8, 0], [8, 12, 1], [10, 15, 0]]}
cases = [
    ('copula.bivariate', {'x':'x','y':'y','family':'gaussian','samples':24,'seed':17,'diagnostics':False}),
    ('1001', {'columns': ['x'], 'sta.bst.ds.ao.0': True, 'sta.bst.ds.ao.1': True}),
    ('1013', {'columns': ['x'], 'sta.bst.ds.hist.bins0': False}),
    ('1406', {'x': 'x', 'y': 'y'}),
    ('1411', {'columns': ['x', 'y'], 'sta.chi.table_combined': '0',
              'tables.ui.tables.residuals': True, 'tables.measures': False,
              'tables.ui.kappaopt': False, 'tables.ui.full2x2': False,
              'tables.plot.bar': '0', 'tables.plot.interaction': False}),
    ('1121', {'columns': ['x', 'y'], 'sta.fa.rot.type': '1', 'retention': 'count', 'threshold': 2}),
    ('1132', {'columns': ['x', 'y'], 'cluster.linkage': '2', 'cluster.linkage.flex.beta': 0,
              'mv.distancemeasure': '5', 'mv.distance.generalized.opt.power': 2,
              'mv.distance.generalized.opt.root': 2, 'mv.noc.opt.singleorrange': '2-3'}),
    ('1620', {'time': 'x', 'status': 'status', 'sta.surv.lt.timeintw': 2, 'sta.surv.lt.maxtime.ui': 8}),
    ('1621', {'time': 'x', 'status': 'status'}),
    ('1704', {'sta.pass.matched_design': True}),
    ('3005', {'columns': ['x', 'y']}),
    ('4018', {'columns': ['x'], 'sta.distr.params.estimate.opt': False,
              'sta.gamma.shapek': 2, 'sta.weibull.scalelambda': 3}),
    ('1102', {'columns': ['x', 'y', 'status'], 'sta.anova.showcontrasts': True}),
    ('1109', {'responses': ['y'], 'predictors': ['x'], 'random_factors': ['status'],
              'sta.reg.show_iter': True}),
]


def compare(left, right, location='result'):
    if isinstance(left, (int, float)) and not isinstance(left, bool):
        if not isinstance(right, (int, float)) or not math.isclose(left, right, rel_tol=1e-10, abs_tol=1e-12):
            raise AssertionError(f'{location}: numerical difference {left!r} vs {right!r}')
    elif isinstance(left, dict):
        if not isinstance(right, dict) or left.keys() != right.keys():
            raise AssertionError(f'{location}: object keys differ')
        for key in left:
            compare(left[key], right[key], f'{location}.{key}')
    elif isinstance(left, list):
        if not isinstance(right, list) or len(left) != len(right):
            raise AssertionError(f'{location}: list length differs')
        for i, (a, b) in enumerate(zip(left, right)):
            compare(a, b, f'{location}[{i}]')
    elif left != right:
        raise AssertionError(f'{location}: values differ')


def main():
    executable = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / ('dist-backend/statworkbench-engine/statworkbench-engine' + ('.exe' if sys.platform == 'win32' else ''))
    requests = '\n'.join(json.dumps({'id': aid, 'method': 'analyze', 'params': {'analysis': aid, 'data': ({'name':'Copula verification','columns':['x','y'],'rows':[[i+1,math.sin(i*.7)+i*.08] for i in range(48)]} if aid=='copula.bivariate' else data), 'options': options}}) for aid, options in cases) + '\n'
    responses = []
    for command in ([sys.executable, '-u', '-m', 'backend.worker'], [str(executable)]):
        run = subprocess.run(command, input=requests, capture_output=True, text=True, cwd=ROOT, timeout=180, check=True)
        messages = [json.loads(line) for line in run.stdout.splitlines()]
        if len(messages) != len(cases) or not all(m.get('ok') for m in messages):
            raise AssertionError(f'Worker failed a representative procedure: {messages}')
        responses.append(messages)
    compare(*responses)
    result = {'verified': True, 'procedures': [aid for aid, _ in cases], 'relativeTolerance': 1e-10,
              'scope': f'Frozen-worker packaging matches source-worker results for {len(cases)} model, survival, data, chart and copula workflows, including native Mann–Whitney rows, histogram bins and crosstab residuals.'}
    output = ROOT / 'test-artifacts/frozen-controls-verification.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
