from __future__ import annotations

import itertools
import re
import subprocess
from pathlib import Path

N_INPUTS = 4  # dimensions of the MDS matrix, e.g., 4 for a 4x4 MDS matrix
N_GATES = 8  # number of XOR gates in the circuit


BREAK_OUTPUT_SYMMETRY = True  # fixed Y1 < Y2 < ... < YN
BREAK_INPUT_SYMMETRY = True  # fixed t1 = x1 + x2

OUTPUT_FILE = Path(__file__).with_name(f"structural_n{N_INPUTS}_k{N_GATES}.cnf")
MAP_FILE = Path(str(OUTPUT_FILE) + ".map")
RESULT_FILE = Path(str(OUTPUT_FILE) + ".result")


def input_name(index: int) -> str:
    return f"X{index + 1}"


def gate_name(index: int) -> str:
    return f"T{index + 1}"


def node_name(node: int) -> str:
    if node < N_INPUTS:
        return input_name(node)
    return gate_name(node - N_INPUTS)


def edge_name(source: int, gate_index: int) -> str:
    return f"edge_{node_name(source)}_{gate_name(gate_index)}"


def flow_name(scenario: int, source: int, target: int) -> str:
    return f"flow_s{scenario}_{node_name(source)}_{node_name(target)}"


def reach_name(gate_index: int, input_index: int) -> str:
    return f"reach_{gate_name(gate_index)}_{input_name(input_index)}"


def depth_name(gate_index: int, limit: int) -> str:
    return f"depth_le_{gate_name(gate_index)}_{limit}"


def output_choice_name(output_index: int, gate_index: int) -> str:
    return f"output_Y{output_index + 1}_{gate_name(gate_index)}"


class CNF:

    def __init__(self) -> None:
        self.name_to_id: dict[str, int] = {}
        self.id_to_name: list[str] = [""]
        self.clauses: list[tuple[int, ...]] = []
        self.cardinality_id = 0
        self.cardinality_variables = 0

    def var(self, name: str) -> int:
        existing = self.name_to_id.get(name)
        if existing is not None:
            return existing
        variable = len(self.id_to_name)
        self.name_to_id[name] = variable
        self.id_to_name.append(name)
        return variable

    def add_clause(self, literals: list[int] | tuple[int, ...]) -> None:
        unique: list[int] = []
        seen: set[int] = set()
        for literal in literals:
            if -literal in seen:
                return
            if literal not in seen:
                seen.add(literal)
                unique.append(literal)
        self.clauses.append(tuple(unique))

    def require_true(self, literal: int) -> None:
        self.add_clause([literal])

    def require_false(self, literal: int) -> None:
        self.add_clause([-literal])

    def fresh_cardinality_prefix(self) -> str:
        prefix = f"card_{self.cardinality_id}"
        self.cardinality_id += 1
        return prefix

    @property
    def variable_count(self) -> int:
        return len(self.id_to_name) - 1


def emit_at_most(cnf: CNF, literals: list[int], count: int) -> None:
    size = len(literals)
    if count < 0:
        cnf.add_clause([])
        return
    if size == 0 or count >= size:
        return
    if count == 0:
        for literal in literals:
            cnf.require_false(literal)
        return

    prefix = cnf.fresh_cardinality_prefix()
    counters: list[list[int]] = []
    for row in range(size - 1):
        current: list[int] = []
        for column in range(count):
            variable = cnf.var(f"{prefix}_s{row + 1}_{column + 1}")
            cnf.cardinality_variables += 1
            current.append(variable)
        counters.append(current)

    cnf.add_clause([-literals[0], counters[0][0]])
    for column in range(1, count):
        cnf.require_false(counters[0][column])

    for row in range(1, size - 1):
        literal = literals[row]
        cnf.add_clause([-literal, counters[row][0]])
        cnf.add_clause([-counters[row - 1][0], counters[row][0]])

        for column in range(1, count):
            cnf.add_clause(
                [
                    -literal,
                    -counters[row - 1][column - 1],
                    counters[row][column],
                ]
            )
            cnf.add_clause([-counters[row - 1][column], counters[row][column]])

        cnf.add_clause([-literal, -counters[row - 1][count - 1]])

    cnf.add_clause([-literals[-1], -counters[-1][count - 1]])


def emit_at_least(cnf: CNF, literals: list[int], count: int) -> None:
    size = len(literals)
    if count <= 0:
        return
    if count > size:
        cnf.add_clause([])
        return
    if count == 1:
        cnf.add_clause(literals)
        return
    if count == 2:
        cnf.add_clause(literals)
        for index, literal in enumerate(literals):
            cnf.add_clause([-literal] + literals[:index] + literals[index + 1 :])
        return

    emit_at_most(cnf, [-literal for literal in literals], size - count)


def emit_exactly(cnf: CNF, literals: list[int], count: int) -> None:
    emit_at_most(cnf, literals, count)
    emit_at_least(cnf, literals, count)


def all_output_choice_names() -> list[str]:
    return [output_choice_name(output_index, gate_index) for output_index in range(N_INPUTS) for gate_index in range(N_GATES)]


def all_edge_names() -> list[str]:
    return [edge_name(source, gate_index) for gate_index in range(N_GATES) for source in range(N_INPUTS + gate_index)]


# ============================================================================
# 拓扑约束
# ============================================================================


def emit_topology_edges(cnf: CNF) -> None:
    for gate_index in range(N_GATES):
        candidates = [cnf.var(edge_name(source, gate_index)) for source in range(N_INPUTS + gate_index)]
        emit_exactly(cnf, candidates, 2)

    if BREAK_INPUT_SYMMETRY:
        cnf.require_true(cnf.var(edge_name(0, 0)))
        cnf.require_true(cnf.var(edge_name(1, 0)))


def emit_output_selection(cnf: CNF) -> None:
    choices_by_output = [[cnf.var(output_choice_name(output_index, gate_index)) for gate_index in range(N_GATES)] for output_index in range(N_INPUTS)]

    for choices in choices_by_output:
        emit_exactly(cnf, choices, 1)

    for gate_index in range(N_GATES):
        emit_at_most(
            cnf,
            [choices_by_output[output_index][gate_index] for output_index in range(N_INPUTS)],
            1,
        )

    if BREAK_OUTPUT_SYMMETRY:
        for earlier_output in range(N_INPUTS - 1):
            later_output = earlier_output + 1
            for earlier_gate in range(N_GATES):
                for later_gate in range(earlier_gate + 1):
                    cnf.add_clause(
                        [
                            -choices_by_output[earlier_output][earlier_gate],
                            -choices_by_output[later_output][later_gate],
                        ]
                    )


def output_uses_for_node(cnf: CNF, node: int) -> tuple[list[int], int]:

    if node < N_INPUTS:
        return [], 0
    gate_index = node - N_INPUTS
    return (
        [cnf.var(output_choice_name(output_index, gate_index)) for output_index in range(N_INPUTS)],
        0,
    )


def emit_or_equivalence(cnf: CNF, output: int, inputs: list[int]) -> None:

    # output -> OR(inputs)
    cnf.add_clause([-output] + inputs)
    # 每个 input -> output
    for literal in inputs:
        cnf.add_clause([-literal, output])


def emit_or_sets_equivalent(cnf: CNF, left: list[int], right: list[int]) -> None:

    for literal in left:
        cnf.add_clause([-literal] + right)
    for literal in right:
        cnf.add_clause([-literal] + left)


def emit_flow_scenario(
    cnf: CNF,
    scenario: int,
    input_subset: tuple[int, ...],
    output_subset: tuple[int, ...],
) -> int:

    node_count = N_INPUTS + N_GATES
    incoming: list[list[int]] = [[] for _ in range(node_count)]
    outgoing: list[list[int]] = [[] for _ in range(node_count)]
    variable_count = 0

    for gate_index in range(N_GATES):
        target = N_INPUTS + gate_index
        for source in range(target):
            flow = cnf.var(flow_name(scenario, source, target))
            edge = cnf.var(edge_name(source, gate_index))
            cnf.add_clause([-flow, edge])
            outgoing[source].append(flow)
            incoming[target].append(flow)
            variable_count += 1

    selected_inputs = set(input_subset)
    selected_outputs = set(output_subset)

    for node in range(node_count):
        if node < N_INPUTS:
            required = 1 if node in selected_inputs else 0
            emit_exactly(cnf, outgoing[node], required)
            continue

        emit_at_most(cnf, incoming[node], 1)
        leaving = list(outgoing[node])
        gate_index = node - N_INPUTS
        leaving.extend(cnf.var(output_choice_name(output_index, gate_index)) for output_index in selected_outputs)

        emit_at_most(cnf, leaving, 1)
        emit_or_sets_equivalent(cnf, incoming[node], leaving)

    return variable_count


def emit_all_structural_minors(cnf: CNF) -> tuple[int, int]:
    scenario = 0
    flow_variables = 0
    for order in range(1, N_INPUTS + 1):
        for inputs in itertools.combinations(range(N_INPUTS), order):
            for outputs in itertools.combinations(range(N_INPUTS), order):
                flow_variables += emit_flow_scenario(cnf, scenario, inputs, outputs)
                scenario += 1
    return scenario, flow_variables


def variable_mapping_lines(cnf: CNF) -> list[str]:
    lines: list[str] = []
    for variable in range(1, cnf.variable_count + 1):
        name = cnf.id_to_name[variable]
        if name.startswith("edge_") or name.startswith("output_"):
            lines.append(f"c var {variable} {name}")
    return lines


def build_dimacs(cnf: CNF, scenarios: int, flow_variables: int) -> str:
    lines = [
        "c MDS circuit topology search CNF",
        (f"c N={N_INPUTS} K={N_GATES} " f"orders={1}..{N_INPUTS}"),
        (f"c scenarios={scenarios} edge_variables={len(all_edge_names())} " f"output_variables={len(all_output_choice_names())} " f"flow_variables={flow_variables} " f"cardinality_variables={cnf.cardinality_variables}"),
    ]
    lines.append(f"p cnf {cnf.variable_count} {len(cnf.clauses)}")
    lines.extend(" ".join(str(literal) for literal in clause) + " 0" for clause in cnf.clauses)
    return "\n".join(lines) + "\n"


def build_mapping(cnf: CNF, scenarios: int, flow_variables: int) -> str:
    lines = [
        "c MDS circuit topology search variable mapping",
        (f"c config N={N_INPUTS} K={N_GATES} " f"variables={cnf.variable_count} " f"clauses={len(cnf.clauses)}"),
        (f"c scenarios={scenarios} edge_variables={len(all_edge_names())} " f"output_variables={len(all_output_choice_names())} " f"flow_variables={flow_variables} " f"cardinality_variables={cnf.cardinality_variables}"),
        "c mapping format: c var <DIMACS ID> <variable name>",
    ]
    lines.extend(variable_mapping_lines(cnf))
    return "\n".join(lines) + "\n"


def build_artifacts() -> tuple[CNF, str, str]:

    cnf = CNF()
    emit_topology_edges(cnf)
    emit_output_selection(cnf)
    scenarios, flow_variables = emit_all_structural_minors(cnf)
    cnf_text = build_dimacs(cnf, scenarios, flow_variables)
    map_text = build_mapping(cnf, scenarios, flow_variables)
    return cnf, cnf_text, map_text


def parse_kissat_model(output: str) -> set[int] | None:
    if re.search(r"^s\s+UNSATISFIABLE\s*$", output, re.MULTILINE):
        return None

    literals = [int(token) for line in output.splitlines() if line.startswith("v ") for token in line[2:].split() if token != "0"]
    return {literal for literal in literals if literal > 0}


def format_circuit(cnf: CNF, true_variables: set[int]) -> str:
    lines = ["Circuit:"]
    for gate_index in range(N_GATES):
        selected = [source for source in range(N_INPUTS + gate_index) if cnf.name_to_id[edge_name(source, gate_index)] in true_variables]

        lines.append(f"{gate_name(gate_index)} = " f"{node_name(selected[0])} + {node_name(selected[1])}")

    for output_index in range(N_INPUTS):
        selected = [gate_index for gate_index in range(N_GATES) if cnf.name_to_id[output_choice_name(output_index, gate_index)] in true_variables]
        lines.append(f"Y{output_index + 1} = {gate_name(selected[0])}")
    return "\n".join(lines)


def solve_cnf() -> str | None:
    cnf, cnf_text, map_text = build_artifacts()
    OUTPUT_FILE.write_text(cnf_text, encoding="utf-8")
    print(f"CNF written to {OUTPUT_FILE}, {len(cnf.clauses)} clauses, {cnf.variable_count} variables.")
    MAP_FILE.write_text(map_text, encoding="utf-8")
    print(f"Variable mapping written to {MAP_FILE}, {len(variable_mapping_lines(cnf))} variables.")
    print(f"Running kissat on {OUTPUT_FILE}...")
    process = subprocess.run(
        ["kissat", "-q", str(OUTPUT_FILE)],
        capture_output=True,
        text=True,
        check=False,
    )
    print(f"kissat finished with return code {process.returncode}.")
    RESULT_FILE.write_text(process.stdout, encoding="utf-8")
    true_variables = parse_kissat_model(process.stdout)
    if true_variables is None:
        return None

    return format_circuit(cnf, true_variables)


def main() -> None:
    circuit = solve_cnf()
    print(circuit if circuit is not None else "UNSAT")


if __name__ == "__main__":
    main()
