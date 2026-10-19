"""Finite-state Markov-chain diagnostics from an observed categorical sequence.

This is an independent, empirical workflow. It describes the transition graph
observed in worksheet rows; it does not establish that the source process is
first-order Markovian or that unobserved transitions are impossible.
"""
from __future__ import annotations

import copy
import math
from collections import deque

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components


_ENTRY = dict(
    id="stochastic.markov_chain",
    name="Markov Chain & Ergodicity",
    category="Time series",
    description="Estimate an empirical finite-state transition matrix and inspect communicating classes, absorbing states, periods, stationary probabilities and ergodicity.",
    coverage="extension",
    provenance="Independent StatWorkbench extension",
    limitations=[
        "States are read from one categorical worksheet column in row order; rows are equally spaced steps.",
        "Transition structure is empirical and depends on observed sample support. This procedure does not test the Markov property or prove that missing edges are impossible.",
        "A unique stationary distribution is reported only when every empirical row is defined and exactly one closed communicating class is observed.",
    ],
    fields=[
        dict(key="column", label="State sequence", type="column", required=True),
        dict(key="step", label="Transition step", type="integer", required=True, default=1, min=1, max=1000),
    ],
)


def catalog():
    return [copy.deepcopy(_ENTRY)]


def _state(value):
    """Canonical typed key; numeric 1 and 1.0 are the same state, text stays distinct."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        return ("boolean", value)
    if isinstance(value, (int, float, np.integer, np.floating)):
        number = float(value)
        if not math.isfinite(number):
            return None
        return ("number", number)
    if isinstance(value, str):
        return ("text", value)
    raise ValueError("State sequence values must be text, numbers, booleans, or blank.")


def _periods(adjacency, labels):
    """Return the period of each strongly connected class, if defined."""
    count, component = connected_components(csr_matrix(adjacency), directed=True, connection="strong")
    periods = [None] * count
    members = [np.flatnonzero(component == group).tolist() for group in range(count)]
    for group, nodes in enumerate(members):
        root = nodes[0]
        distance = {root: 0}
        queue = deque([root])
        while queue:
            source = queue.popleft()
            for target in np.flatnonzero(adjacency[source]).tolist():
                if component[target] == group and target not in distance:
                    distance[target] = distance[source] + 1
                    queue.append(target)
        period = 0
        for source in nodes:
            for target in np.flatnonzero(adjacency[source]).tolist():
                if component[target] == group:
                    period = math.gcd(period, abs(distance[source] + 1 - distance[target]))
        periods[group] = period or None
    return count, component, members, periods


def analyze(analysis_id, data, options=None):
    if str(analysis_id) != _ENTRY["id"]:
        raise ValueError("Unknown stochastic analysis identifier.")
    options = options or {}
    if not isinstance(options, dict):
        raise ValueError("Analysis options must be an object.")
    columns = data.get("columns", [])
    if not isinstance(columns, list) or len(set(columns)) != len(columns):
        raise ValueError("Dataset needs unique, nonempty column names.")
    column = options.get("column")
    if not isinstance(column, str) or column not in columns:
        raise ValueError("Choose a state-sequence column from the dataset.")
    raw_step = options.get("step", 1)
    if isinstance(raw_step, bool):
        raise ValueError("Transition step must be an integer between 1 and 1,000.")
    try:
        numeric_step = float(raw_step)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Transition step must be an integer between 1 and 1,000.") from None
    if not math.isfinite(numeric_step) or int(numeric_step) != numeric_step or not 1 <= numeric_step <= 1000:
        raise ValueError("Transition step must be an integer between 1 and 1,000.")
    step = int(numeric_step)

    frame = pd.DataFrame(data.get("rows", []), columns=columns)
    sequence = [_state(value) for value in frame[column].tolist()]
    states = []
    state_indices = {}
    for state in sequence:
        if state is not None and state not in state_indices:
            state_indices[state] = len(states)
            states.append(state)
    if not states:
        raise ValueError("The selected sequence has no observed states.")
    if len(states) > 50:
        raise ValueError("The selected sequence has more than 50 distinct states; select a smaller state space.")
    if len(sequence) <= step:
        raise ValueError("The sequence must contain at least one pair separated by the transition step.")

    display = []
    base_labels = [format(state[1], "g") if state[0] == "number" else str(state[1]) for state in states]
    clipped_labels = [len(label) > 200 for label in base_labels]
    base_labels = [label[:197] + "..." if clipped else label
                   for label, clipped in zip(base_labels, clipped_labels)]
    collisions = {label for label in base_labels if base_labels.count(label) > 1}
    for index, (state, label) in enumerate(zip(states, base_labels), 1):
        display.append(f"{label} [{state[0]} {index}]" if label in collisions else label)

    k = len(states)
    counts = np.zeros((k, k), dtype=int)
    omitted = 0
    for i in range(len(sequence) - step):
        before, after = sequence[i], sequence[i + step]
        if before is None or after is None:
            omitted += 1
            continue
        counts[state_indices[before], state_indices[after]] += 1
    valid_transitions = int(counts.sum())
    if valid_transitions == 0:
        raise ValueError("No transitions have two observed endpoint states at the selected step.")

    outgoing = counts.sum(axis=1)
    probabilities = np.full((k, k), np.nan, dtype=float)
    defined = outgoing > 0
    probabilities[defined] = counts[defined] / outgoing[defined, None]
    adjacency = counts > 0
    class_count, component, members, periods = _periods(adjacency, states)
    irreducible = class_count == 1
    all_rows_defined = bool(np.all(defined))
    period = periods[0] if irreducible else None
    aperiodic = period == 1 if irreducible else None
    ergodic = bool(irreducible and aperiodic and all_rows_defined)

    outgoing_to_other = [False] * class_count
    for source in range(k):
        for target in np.flatnonzero(adjacency[source]).tolist():
            if component[source] != component[target]:
                outgoing_to_other[component[source]] = True
    closed = [not outgoing_to_other[group] for group in range(class_count)]
    # An unobserved outgoing row makes closure unknowable from this sample.
    if not all_rows_defined:
        closed = [None if any(not defined[node] for node in members[group]) else value
                  for group, value in enumerate(closed)]

    unique_stationary = bool(all_rows_defined and sum(value is True for value in closed) == 1)
    stationary = None
    if unique_stationary:
        system = np.vstack([probabilities.T - np.eye(k), np.ones((1, k))])
        target = np.r_[np.zeros(k), 1.]
        estimate = np.linalg.lstsq(system, target, rcond=None)[0]
        estimate = np.maximum(estimate, 0.)
        total = float(estimate.sum())
        if total > 0 and np.isfinite(total):
            stationary = estimate / total

    result = {
        "analysis": _ENTRY["id"],
        "title": _ENTRY["name"],
        "tables": [
            dict(title="Transition counts", columns=["From \\ To"] + display,
                 rows=[[display[i]] + counts[i].tolist() for i in range(k)]),
            dict(title="Empirical transition probabilities", columns=["From \\ To"] + display,
                 rows=[[display[i]] + [None if not np.isfinite(value) else round(float(value), 8)
                                        for value in probabilities[i]] for i in range(k)]),
            dict(title="State and communicating-class diagnostics",
                 columns=["State", "Observed outgoing transitions", "Observed absorbing", "Communicating class", "Class size", "Class period", "Class closed"],
                 rows=[[display[i], int(outgoing[i]), bool(outgoing[i] > 0 and counts[i, i] == outgoing[i]),
                        int(component[i]) + 1, len(members[component[i]]), periods[component[i]], closed[component[i]]]
                       for i in range(k)]),
            dict(title="Stationary probabilities" if stationary is not None else "Stationary probabilities (not identified)",
                 columns=["State", "Probability"],
                 rows=[[display[i], round(float(stationary[i]), 8) if stationary is not None else None]
                       for i in range(k)]),
            dict(title="Chain summary", columns=["Diagnostic", "Result"], rows=[
                ["Sequence rows", len(sequence)], ["Transition step", step],
                ["Observed states", k], ["Usable transitions", valid_transitions],
                ["Pairs omitted for missing endpoints", omitted],
                ["All empirical rows defined", all_rows_defined],
                ["Communicating classes", class_count], ["Irreducible on observed states", irreducible],
                ["Irreducible-class period", period], ["Aperiodic", aperiodic],
                ["Ergodic on observed support", ergodic],
                ["Stationary distribution unique and estimated", stationary is not None],
            ]),
        ],
        "charts": [],
        "notes": [
            "The row order is treated as equally spaced time. Each transition pairs rows t and t+step; missing endpoints omit that pair.",
            "Communicating classes, periods, closed classes, absorbing states and ergodicity describe the graph supported by observed transitions. They are sample diagnostics, not proof about unobserved possibilities or the generating process.",
        ],
        "warnings": [],
    }
    if any(clipped_labels):
        result["notes"].append("State labels longer than 200 characters are shortened in result tables; the analysis uses their full original values.")
    if omitted:
        result["warnings"].append(f"Omitted {omitted} transition pairs with at least one missing or blank endpoint.")
    if not all_rows_defined:
        missing_states = [display[i] for i in range(k) if not defined[i]]
        result["warnings"].append("No observed outgoing transition for: " + ", ".join(missing_states) + ". Their empirical probability rows, class closure, ergodicity and stationary probabilities are not identified.")
    elif not irreducible and not unique_stationary:
        result["warnings"].append("The observed transition graph is reducible with multiple closed communicating classes; a single stationary distribution is not identified without additional assumptions about the initial class weights.")
    elif not irreducible and unique_stationary:
        result["notes"].append("The observed graph is reducible but has one closed communicating class, so the estimated stationary distribution is unique and assigns zero mass to transient states.")
    elif period != 1:
        result["warnings"].append(f"The observed irreducible chain has period {period}; a unique stationary distribution exists, but the distribution of the chain need not converge to it from every starting state.")
    return result
