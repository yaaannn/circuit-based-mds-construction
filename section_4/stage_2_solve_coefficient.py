import math
import re
import subprocess
from itertools import combinations
from pathlib import Path

from sage.all import GF, Matrix, PolynomialRing

# Configuration

CIRCUIT = """
t1 = x3 + x4
t2 = x1 + x2
t3 = x3 + t2
t4 = t1 + t3    (y1)
t5 = x1 + t1
t6 = t2 + t5    (y2)
t7 = t4 + t5    (y3)
t8 = t3 + t6    (y4)
"""

BASE_DIR = Path(__file__).resolve().parent
POLYNOMIAL_FILE = BASE_DIR / "polynomials.txt"
SMT_FILE = BASE_DIR / "coefficient_constraints.smt2"
RESULT_FILE = BASE_DIR / "result.txt"

FIELD_BITS = 4  # bitsize
PRIMITIVE_POLYNOMIAL = 0x13  # primitive polynomial
MAX_ABS_EXPONENT: int | None = 1  # # limit for coefficient exponents (e.g., 1 means coefficients 0, +1, -1(14); None means no limit)
MAX_TOTAL_COST: int | None = 3  # # limit for total cost of coefficients; None means no limit


SIGNED_EXPONENT_COSTS = {
    4: {
        0: 0,
        1: 1,
        2: 2,
        3: 3,
        4: 4,
        5: 5,
        6: 4,
        7: 4,
        -7: 4,
        -6: 4,
        -5: 5,
        -4: 4,
        -3: 3,
        -2: 2,
        -1: 1,
    },
    8: {
        0: 0,
        1: 2,
        2: 4,
        3: 5,
        4: 7,
        5: 9,
        6: 10,
        -6: 10,
        -5: 9,
        -4: 7,
        -3: 5,
        -2: 4,
        -1: 2,
    },
}

GATE_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\s*\+\s*" r"([A-Za-z_]\w*)\s*(?:\(\s*[yY](\d+)\s*\))?\s*(?:#.*)?$")
INPUT_RE = re.compile(r"x([1-9]\d*)$")
VARIABLE_RE = re.compile(r"([ab]\d+)(?:\^(\d+))?")
MODEL_VALUE_RE = re.compile(r"\((a\d+|b\d+|TOTAL_COST)\s+" r"(#x[0-9A-Fa-f]+|#b[01]+|\(_\s+bv\d+\s+\d+\))\)")


# Circuit to symbolic minors


def parse_circuit(text):
    records = []
    input_indices = set()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = GATE_RE.fullmatch(line)
        if match is None:
            continue
        target, left, right, output_index = match.groups()
        records.append((target, left, right, output_index))
        for operand in (left, right):
            input_match = INPUT_RE.fullmatch(operand)
            if input_match is not None:
                input_indices.add(int(input_match.group(1)))

    input_count = max(input_indices)
    gates = [(target, left, right) for target, left, right, _ in records]
    outputs = {int(output_index): target for target, _left, _right, output_index in records if output_index is not None}
    return gates, input_count, [outputs[index] for index in range(1, input_count + 1)]


def build_symbolic_matrix(gates, input_count, outputs):
    variable_names = [name for gate_index in range(1, len(gates) + 1) for name in (f"a{gate_index}", f"b{gate_index}")]
    ring = PolynomialRing(GF(2), names=variable_names)
    symbols = ring.gens_dict()

    values = {f"x{input_index + 1}": [ring.one() if coordinate == input_index else ring.zero() for coordinate in range(input_count)] for input_index in range(input_count)}

    for gate_index, (target, left, right) in enumerate(gates, 1):
        a = symbols[f"a{gate_index}"]
        b = symbols[f"b{gate_index}"]
        values[target] = [a * left_value + b * right_value for left_value, right_value in zip(values[left], values[right])]

    return Matrix(ring, [values[output] for output in outputs])


def polynomial_sort_key(polynomial):
    return (
        polynomial.total_degree(),
        len(polynomial.monomials()),
        str(polynomial),
    )


def generate_constraints(matrix):
    constraints = set()
    determinant_count = 0

    for order in range(1, matrix.nrows() + 1):
        for rows in combinations(range(matrix.nrows()), order):
            for columns in combinations(range(matrix.ncols()), order):
                determinant_count += 1
                minor = matrix.matrix_from_rows_and_columns(rows, columns)
                determinant = minor.det()
                if determinant.is_zero():
                    readable_rows = tuple(index + 1 for index in rows)
                    readable_columns = tuple(index + 1 for index in columns)
                    return [], determinant_count, (order, readable_rows, readable_columns)

                for factor, _multiplicity in determinant.factor():
                    if not factor.is_one() and len(factor.monomials()) > 1:
                        constraints.add(factor)

    return sorted(constraints, key=polynomial_sort_key), determinant_count, None


def write_polynomials(path, gates, input_count, outputs, constraints, minor_count):
    lines = [
        "# MDS coefficient constraints over a characteristic-two extension field",
        f"# inputs={input_count}",
        f"# outputs={','.join(outputs)}",
        f"# gates={len(gates)}",
        f"# minors={minor_count}",
        f"# constraints={len(constraints)}",
        "# Each non-comment line is a polynomial required to be nonzero.",
        "",
        *(str(polynomial) for polynomial in constraints),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# Polynomial representation used by the SMT encoder


def parse_polynomial(polynomial):
    parity = {}
    for raw_term in str(polynomial).split("+"):
        term = raw_term.strip()
        if term == "1":
            factors = ()
        else:
            expanded = []
            for raw_factor in term.split("*"):
                match = VARIABLE_RE.fullmatch(raw_factor.strip())
                name, power_text = match.groups()
                expanded.extend([name] * (int(power_text) if power_text else 1))
            factors = tuple(sorted(expanded))
        parity[factors] = not parity.get(factors, False)
    return sorted(factors for factors, is_odd in parity.items() if is_odd)


def bv(value, width):
    return f"(_ bv{value} {width})"


def balanced(operator, expressions):
    current = list(expressions)
    while len(current) > 1:
        current = [(current[index] if index + 1 == len(current) else f"({operator} {current[index]} {current[index + 1]})") for index in range(0, len(current), 2)]
    return current[0]


def generate_power_table():
    order = (1 << FIELD_BITS) - 1
    reduction = PRIMITIVE_POLYNOMIAL & order
    values = []
    value = 1
    for _ in range(order):
        values.append(value)
        carry = value & (1 << (FIELD_BITS - 1))
        value = (value << 1) & order
        if carry:
            value ^= reduction
    return values


def emit_lookup(name, input_width, output_width, values):
    lines = [f"(define-fun {name} ((x (_ BitVec {input_width}))) " f"(_ BitVec {output_width})"]
    for index, value in enumerate(values):
        lines.append(f"  (ite (= x {bv(index, input_width)}) " f"{bv(value, output_width)}")
    lines.append(f"       {bv(0, output_width)}" + ")" * len(values))
    lines.append(")")
    return lines


def emit_sparse_lookup(name, input_width, output_width, values):
    lines = [f"(define-fun {name} ((x (_ BitVec {input_width}))) " f"(_ BitVec {output_width})"]
    for input_value, output_value in sorted(values.items()):
        lines.append(f"  (ite (= x {bv(input_value, input_width)}) " f"{bv(output_value, output_width)}")
    lines.append(f"       {bv(0, output_width)}" + ")" * len(values))
    lines.append(")")
    return lines


def allowed_exponents(order):
    if MAX_ABS_EXPONENT is None:
        return list(range(order))
    positive = set(range(MAX_ABS_EXPONENT + 1))
    negative = {order - distance for distance in range(1, MAX_ABS_EXPONENT + 1)}
    return sorted(positive | negative)


def exponent_costs(order, permitted):
    signed_costs = SIGNED_EXPONENT_COSTS.get(FIELD_BITS, {})
    configured = {signed_exponent % order: cost for signed_exponent, cost in signed_costs.items()}
    return {exponent: configured.get(exponent, min(exponent, order - exponent)) for exponent in permitted}


def build_shared_exponent_dag(polynomials, order):
    add_width = FIELD_BITS + 1
    expression_by_monomial = {(): bv(0, FIELD_BITS)}
    definitions = []

    def intern(monomial):
        if monomial in expression_by_monomial:
            return expression_by_monomial[monomial]
        if len(monomial) == 1:
            expression_by_monomial[monomial] = monomial[0]
            return monomial[0]

        middle = len(monomial) // 2
        left = intern(monomial[:middle])
        right = intern(monomial[middle:])
        exponent_sum = f"(bvadd ((_ zero_extend 1) {left}) " f"((_ zero_extend 1) {right}))"
        reduced = f"(bvurem {exponent_sum} {bv(order, add_width)})"
        expression = f"((_ extract {FIELD_BITS - 1} 0) {reduced})"
        name = f"MONO_EXP_{len(definitions) + 1}"
        definitions.append(f"(define-fun {name} () (_ BitVec {FIELD_BITS}) {expression})")
        expression_by_monomial[monomial] = name
        return name

    for polynomial in polynomials:
        for monomial in polynomial:
            intern(monomial)
    return expression_by_monomial, definitions


# SMT generation


def build_smt(constraints, gate_count):
    polynomials = [parse_polynomial(constraint) for constraint in constraints]
    order = (1 << FIELD_BITS) - 1
    permitted = allowed_exponents(order)
    costs = exponent_costs(order, permitted)
    variables = [name for gate_index in range(1, gate_count + 1) for name in (f"a{gate_index}", f"b{gate_index}")]

    maximum_cost = len(variables) * max(costs.values())
    cost_width = max(1, math.ceil(math.log2(maximum_cost + 1)))
    exponent_by_monomial, exponent_definitions = build_shared_exponent_dag(
        polynomials,
        order,
    )

    lines = [
        ";; Automatically generated coefficient constraints",
        ";; a_i and b_i store exponents; exponent 0 denotes coefficient 1",
        "(set-logic QF_BV)",
        "(set-option :produce-models true)",
        "",
    ]
    lines.extend(f"(declare-fun {variable} () (_ BitVec {FIELD_BITS}))" for variable in variables)
    lines.append("")

    for variable in variables:
        choices = " ".join(f"(= {variable} {bv(exponent, FIELD_BITS)})" for exponent in permitted)
        lines.append(f"(assert (or {choices}))")
    lines.append("")

    lines.extend(
        emit_lookup(
            "power_table",
            FIELD_BITS,
            FIELD_BITS,
            generate_power_table(),
        )
    )
    lines.append("")
    lines.extend(exponent_definitions)
    lines.append("")

    lines.extend(
        emit_sparse_lookup(
            "coefficient_cost",
            FIELD_BITS,
            cost_width,
            costs,
        )
    )
    cost_terms = [f"(coefficient_cost {variable})" for variable in variables]
    lines.append(f"(define-fun TOTAL_COST () (_ BitVec {cost_width}) " f"{balanced('bvadd', cost_terms)})")
    if MAX_TOTAL_COST is not None:
        lines.append(f"(assert (bvule TOTAL_COST {bv(MAX_TOTAL_COST, cost_width)}))")
    lines.append("")

    for index, polynomial in enumerate(polynomials, 1):
        if len(polynomial) == 2:
            left, right = (exponent_by_monomial[monomial] for monomial in polynomial)
            predicate = f"(distinct {left} {right})"
        else:
            field_terms = [f"(power_table {exponent_by_monomial[monomial]})" for monomial in polynomial]
            predicate = f"(distinct {balanced('bvxor', field_terms)} " f"{bv(0, FIELD_BITS)})"
        lines.append(f"(assert (! {predicate} :named poly_{index}))")

    lines.extend(
        [
            "",
            "(check-sat)",
            f"(get-value ({' '.join([*variables, 'TOTAL_COST'])}))",
            "(get-info :all-statistics)",
        ]
    )
    return "\n".join(lines) + "\n"


# Solving and result parsing


def parse_bit_vector(value):
    if value.startswith("#x"):
        return int(value[2:], 16)
    if value.startswith("#b"):
        return int(value[2:], 2)
    match = re.search(r"bv(\d+)", value)
    return int(match.group(1)) if match is not None else 0


def parse_result(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    status = lines[0] if lines else "error"
    values = {name: parse_bit_vector(value) for name, value in MODEL_VALUE_RE.findall(text)}
    return {"status": status, "values": values, "raw": text}


def solve(smt_file=SMT_FILE, result_file=RESULT_FILE):
    try:
        process = subprocess.run(
            ["z3", "-smt2", str(smt_file)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        text = f"error\n{error}\n"
        result_file.write_text(text, encoding="utf-8")
        return parse_result(text)

    text = process.stdout
    if process.stderr:
        text += process.stderr
    result_file.write_text(text, encoding="utf-8")
    return parse_result(text)


def signed_exponent(exponent):
    order = (1 << FIELD_BITS) - 1
    return exponent if exponent <= order // 2 else exponent - order


def coefficient_term(signal, exponent):
    exponent = signed_exponent(exponent)
    if exponent == 0:
        return signal
    return f"L^{exponent}*{signal}"


def coefficient_name(exponent):
    exponent = signed_exponent(exponent)
    return "1" if exponent == 0 else f"L^{exponent}"


def print_solution(solution, gates, outputs):
    status = solution["status"]
    print(f"Solver status: {status}")
    if status != "sat":
        return

    values = solution["values"]
    if "TOTAL_COST" in values:
        print(f"Total cost: {values['TOTAL_COST']}")

    print("Coefficients:")
    for index in range(1, len(gates) + 1):
        a = coefficient_name(values.get(f"a{index}", 0))
        b = coefficient_name(values.get(f"b{index}", 0))
        print(f"a{index} = {a}, b{index} = {b}")

    output_indices = {name: index for index, name in enumerate(outputs, 1)}
    print("Circuit:")
    for index, (target, left, right) in enumerate(gates, 1):
        expression = f"{target} = {coefficient_term(left, values.get(f'a{index}', 0))}" f" + {coefficient_term(right, values.get(f'b{index}', 0))}"
        if target in output_indices:
            expression += f"    (y{output_indices[target]})"
        print(expression)


def main():
    gates, input_count, outputs = parse_circuit(CIRCUIT)
    matrix = build_symbolic_matrix(gates, input_count, outputs)
    constraints, minor_count, zero_minor = generate_constraints(matrix)

    if zero_minor is not None:
        order, rows, columns = zero_minor
        print("The topology has an identically zero minor: " f"order={order}, rows={rows}, columns={columns}")
        return

    write_polynomials(
        POLYNOMIAL_FILE,
        gates,
        input_count,
        outputs,
        constraints,
        minor_count,
    )
    SMT_FILE.write_text(build_smt(constraints, len(gates)), encoding="utf-8")

    solution = solve()
    print_solution(solution, gates, outputs)


if __name__ == "__main__":
    main()
