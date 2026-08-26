import itertools
import re

from sage.all import GF, FractionField, Matrix, PolynomialRing, identity_matrix

COST_TABLES = {
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
        -5: 9,
        -4: 7,
        -3: 5,
        -2: 4,
        -1: 2,
    },
}


def get_cost_table(bitsize):
    return COST_TABLES.get(bitsize, {})


P = PolynomialRing(GF(2), "L")
K = FractionField(P)
L = K.gen()

GATE_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\s*\+\s*" r"([A-Za-z_]\w*)\s*(?:\(\s*[yY](\d+)\s*\))?\s*(?:#.*)?$")


def gen_binary_matrix(positions, ncols=None):
    if ncols is None:
        ncols = max((max(row) if row else 0) for row in positions)

    matrix = []
    for row_positions in positions:
        row = [0] * ncols
        for column in row_positions:
            row[column - 1] = 1
        matrix.append(row)
    return matrix


def get_binary_matrix(bitsize, case):
    positions = case["binary_matrix_positions"][bitsize]
    return Matrix(GF(2), bitsize, bitsize, gen_binary_matrix(positions, bitsize))


def parse_circuit(text, matrix_order):
    gates = []
    outputs = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        match = GATE_RE.fullmatch(line)
        destination, left, right, output_index = match.groups()
        gates.append((destination, left, right))
        if output_index is not None:
            outputs[int(output_index)] = destination

    missing_outputs = [index for index in range(1, matrix_order + 1) if index not in outputs]
    if missing_outputs:
        missing = ", ".join(f"y{index}" for index in missing_outputs)
        raise ValueError(f"电路缺少输出：{missing}")

    return gates, [outputs[index] for index in range(1, matrix_order + 1)]


def build_matrix(gates, outputs, exp_a, exp_b, matrix_order):
    inputs = [f"x{i}" for i in range(1, matrix_order + 1)]
    expressions = {input_name: [K.one() if coordinate == input_index else K.zero() for coordinate in range(matrix_order)] for input_index, input_name in enumerate(inputs)}

    for gate_index, (destination, left, right) in enumerate(gates):
        a = L ** int(exp_a[gate_index])
        b = L ** int(exp_b[gate_index])
        expressions[destination] = [a * left_value + b * right_value for left_value, right_value in zip(expressions[left], expressions[right])]

    return Matrix(K, [expressions[output] for output in outputs])


def get_minor_factors(matrix, matrix_order):
    factors = set()
    factored_numerators = set()
    indices = range(matrix_order)

    for size in range(1, matrix_order + 1):
        for rows in itertools.combinations(indices, size):
            for columns in itertools.combinations(indices, size):
                minor = matrix.matrix_from_rows_and_columns(rows, columns)
                determinant = K(minor.det())
                if determinant == 0:
                    return None
                numerator = P(determinant.numerator())
                if numerator in factored_numerators:
                    continue
                factored_numerators.add(numerator)
                for factor, _multiplicity in numerator.factor():
                    factor = P(factor)
                    if factor.degree() > 0:
                        factors.add(factor)

    return sorted(
        factors,
        key=lambda poly: (poly.degree(), len(poly.monomials()), str(poly)),
    )


def check_factors_over_binary_matrix(poly_list, binary_matrix, bitsize):
    identity = identity_matrix(GF(2), bitsize)
    power_cache = {0: identity, 1: binary_matrix}

    def matrix_power(degree):
        while degree not in power_cache:
            next_degree = len(power_cache)
            power_cache[next_degree] = power_cache[next_degree - 1] * binary_matrix
        return power_cache[degree]

    for poly_expr in poly_list:
        value = Matrix(GF(2), bitsize, bitsize, 0)
        for degree, coefficient in enumerate(P(poly_expr).list()):
            if coefficient != 0:
                value += matrix_power(degree)
        if not value.is_invertible():
            return False
    return True


def implementation_cost(
    gate_num,
    bit_size,
    exp_a,
    exp_b,
    binary_matrix,
    signed_exponent_costs,
):
    matrix_l_xor_count = sum(max(0, sum(map(int, row)) - 1) for row in binary_matrix.rows())
    l_xor_count = signed_exponent_costs.get(1, matrix_l_xor_count)
    exponents = [int(exponent) for exponent in (*exp_a, *exp_b)]
    coefficient_cost = sum(signed_exponent_costs.get(exponent, abs(exponent) * l_xor_count) for exponent in exponents)
    gate_cost = gate_num * bit_size
    return gate_cost + coefficient_cost, gate_num, bit_size, coefficient_cost


def verify_case(case, matrix_order):
    gates, outputs = parse_circuit(case["circuit"], matrix_order)
    matrix = build_matrix(
        gates,
        outputs,
        case["exp_a"],
        case["exp_b"],
        matrix_order,
    )
    poly_list = get_minor_factors(matrix, matrix_order)

    results = []
    for dimension in case["dimensions"]:
        binary_matrix = get_binary_matrix(dimension, case)
        is_mds = poly_list is not None and check_factors_over_binary_matrix(
            poly_list,
            binary_matrix,
            dimension,
        )
        cost = implementation_cost(
            len(gates),
            dimension,
            case["exp_a"],
            case["exp_b"],
            binary_matrix,
            get_cost_table(dimension),
        )
        results.append((dimension, is_mds, cost))
    return results


def run_cases(cases, matrix_order):
    for case in cases:
        name = case.get("name")
        for dimension, is_mds, cost in verify_case(case, matrix_order):
            conclusion = "MDS" if is_mds else "Not MDS"
            total, gate_num, bit_size, coefficient_cost = cost
            print(f"{name}, L: {dimension} bit, result: {conclusion}, " f"cost: {gate_num}*{bit_size}+{coefficient_cost}={total}")
    print("========================")


class BinaryMatrixPositions(list):
    def __add__(self, other):
        return BinaryMatrixPositions([sorted(set(left).symmetric_difference(right)) for left, right in zip(self, other)])


def companion_positions(size):
    return BinaryMatrixPositions([[size], *[[row] for row in range(1, size)]])


def entry_factory(size):
    def entry(row, column):
        positions = [[] for _ in range(size)]
        positions[row - 1] = [column]
        return BinaryMatrixPositions(positions)

    return entry


C4, C8, C16, C32, C64 = (companion_positions(size) for size in (4, 8, 16, 32, 64))
E4, E8, E16, E32, E64 = (entry_factory(size) for size in (4, 8, 16, 32, 64))
