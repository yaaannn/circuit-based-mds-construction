from __future__ import annotations

import itertools
import re
import subprocess
from itertools import combinations
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).resolve().parent
SMT_FILE = SCRIPT_DIR / "output.smt2"
RESULT_FILE = SCRIPT_DIR / "result.txt"

GF_ALOG = [0x1, 0x2, 0x4, 0x8, 0x3, 0x6, 0xC, 0xB, 0x5, 0xA, 0x7, 0xE, 0xF, 0xD, 0x9, 0x0]
GF_LOG = [0xF, 0x0, 0x1, 0x4, 0x2, 0x8, 0x5, 0xA, 0x3, 0xE, 0x9, 0x7, 0x6, 0xD, 0xB, 0xC]
COST_LUT = [0, 0, 1, 4, 2, 4, 5, 5, 3, 1, 4, 4, 4, 2, 4, 3]


def field_bv(value: int) -> str:
    return f"#x{value & (16 - 1):x}"


def bv(value: int, bits: int) -> str:
    return f"(_ bv{value} {bits})"


class SMT:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def emit(self, line: str = "") -> None:
        self.lines.append(line)

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def balanced(op: str, terms: list[str]) -> str:
    if len(terms) == 1:
        return terms[0]
    middle = len(terms) // 2
    return f"({op} {balanced(op, terms[:middle])} {balanced(op, terms[middle:])})"


def emit_lut(s: SMT, name: str, table: list[int]) -> None:
    s.emit(f"(define-fun {name} ((x (_ BitVec 4))) (_ BitVec 4)")
    for key, value in enumerate(table[:-1]):
        s.emit(f"  (ite (= x {field_bv(key)}) {field_bv(value)}")
    s.emit(f"       {field_bv(table[-1])}" + ")" * (16 - 1))
    s.emit(")")
    s.emit()


def emit_field_library(s: SMT) -> None:
    s.emit("(set-option :produce-models true)")
    s.emit("(set-logic QF_BV)")
    s.emit()
    emit_lut(s, "gf_log", GF_LOG)
    emit_lut(s, "gf_alog", GF_ALOG)

    log_sum = "(bvadd ((_ zero_extend 1) (gf_log x)) ((_ zero_extend 1) (gf_log y)))"
    reduced = f"(ite (bvuge {log_sum} {bv(15, 5)}) " f"(bvsub {log_sum} {bv(15, 5)}) {log_sum})"
    exponent = f"((_ extract 3 0) {reduced})"
    s.emit("(define-fun gf_mul ((x (_ BitVec 4)) (y (_ BitVec 4))) (_ BitVec 4)")
    s.emit(f"  (ite (or (= x #x0) (= y #x0)) #x0 (gf_alog {exponent})))")
    s.emit()


def emit_mul(s: SMT, size: int) -> None:
    args = " ".join(f"(x{i} (_ BitVec 4))" for i in range(size))
    body = balanced("gf_mul", [f"x{i}" for i in range(size)])
    s.emit(f"(define-fun mul{size} ({args}) (_ BitVec 4)")
    s.emit(f"  {body})")
    s.emit()


def emit_determinant(s: SMT, size: int) -> None:
    args = " ".join(f"(m{row}{col} (_ BitVec 4))" for row in range(size) for col in range(size))
    products = [f"(mul{size} " + " ".join(f"m{row}{permutation[row]}" for row in range(size)) + ")" for permutation in itertools.permutations(range(size))]
    s.emit(f"(define-fun det{size} ({args}) (_ BitVec 4)")
    s.emit(f"  {balanced('bvxor', products)})")
    s.emit()


def emit_inputs(s: SMT, n: int) -> None:
    s.emit("; inputs")
    for row in range(n):
        for col in range(n):
            value = 1 if row == col else 0
            s.emit(f"(define-fun X{row + 1}_{col} () (_ BitVec 4) {field_bv(value)})")
    s.emit()


def emit_index(s: SMT, name: str, candidate_count: int) -> None:
    s.emit(f"(declare-fun {name} () (_ BitVec {8}))")
    s.emit(f"(assert (bvult {name} {bv(candidate_count, 8)}))")


def pick(index: str, terms: list[str]) -> str:
    expression = terms[-1]
    for position in reversed(range(len(terms) - 1)):
        expression = f"(ite (= {index} {bv(position, 8)}) " f"{terms[position]} {expression})"
    return expression


def candidates(n: int, gate_count: int) -> list[str]:
    return [f"X{i}" for i in range(1, n + 1)] + [f"T{i}" for i in range(1, gate_count + 1)]


def coefficient_range(limit: Optional[int]) -> list[int]:
    if limit is None:
        return list(range(1, 16))

    return sorted({GF_ALOG[exponent % 15] for exponent in range(-limit, limit + 1)})


def emit_gate(s: SMT, n: int, gate: int, coefficients: list[int]) -> None:
    name = f"T{gate}"
    nodes = candidates(n, gate - 1)
    idx_u = f"idx_{name}_U"
    idx_v = f"idx_{name}_V"

    emit_index(s, idx_u, len(nodes))
    emit_index(s, idx_v, len(nodes))
    s.emit(f"(assert (bvult {idx_u} {idx_v}))")
    s.emit()

    for side, index in (("U", idx_u), ("V", idx_v)):
        for col in range(n):
            terms = [f"{node}_{col}" for node in nodes]
            s.emit(f"(define-fun {name}{side}_{col} () (_ BitVec 4) " f"{pick(index, terms)})")
    s.emit()

    for coefficient in (f"a{gate}", f"b{gate}"):
        s.emit(f"(declare-fun {coefficient} () (_ BitVec 4))")
        choices = " ".join(f"(= {coefficient} {field_bv(value)})" for value in coefficients)
        s.emit(f"(assert (or {choices}))")
    s.emit()

    for col in range(n):
        s.emit(f"(define-fun {name}_{col} () (_ BitVec 4) " f"(bvxor (gf_mul a{gate} {name}U_{col}) " f"(gf_mul b{gate} {name}V_{col})))")
    s.emit()


def emit_output(
    s: SMT,
    n: int,
    k: int,
    output: int,
    previous_index: Optional[str],
) -> str:
    name = f"Y{output}"
    index = f"idx_{name}"
    nodes = candidates(n, k)
    emit_index(s, index, len(nodes))
    if previous_index is not None:
        s.emit(f"(assert (bvult {previous_index} {index}))")

    for col in range(n):
        terms = [f"{node}_{col}" for node in nodes]
        s.emit(f"(define-fun {name}_{col} () (_ BitVec 4) " f"{pick(index, terms)})")
    s.emit()
    return index


def emit_mds_constraints(s: SMT, n: int) -> None:
    outputs = [f"Y{i}" for i in range(1, n + 1)]
    for row in outputs:
        for col in range(n):
            s.emit(f"(assert (not (= {row}_{col} #x0)))")
    s.emit()

    for size in range(2, n + 1):
        for rows in combinations(range(n), size):
            for cols in combinations(range(n), size):
                args = " ".join(f"{outputs[row]}_{col}" for row in rows for col in cols)
                s.emit(f"(assert (not (= (det{size} {args}) #x0)))")
        s.emit()


def emit_cost_constraint(s: SMT, k: int, budget: int) -> None:
    emit_lut(s, "map_ele_cost", COST_LUT)
    s.emit("(define-fun zext_cost ((c (_ BitVec 4))) " "(_ BitVec 8) (concat #x0 c))")
    s.emit()

    terms = [f"(zext_cost (map_ele_cost {coefficient}{gate}))" for gate in range(1, k + 1) for coefficient in ("a", "b")]
    total = balanced("bvadd", terms) if terms else bv(0, 8)
    s.emit(f"(define-fun TOTAL_COST () (_ BitVec 8) {total})")
    s.emit(f"(assert (bvule TOTAL_COST {bv(budget, 8)}))")
    s.emit()


def emit_query(s: SMT, n: int, k: int, include_cost: bool) -> None:
    values = [
        item
        for gate in range(1, k + 1)
        for item in (
            f"idx_T{gate}_U",
            f"idx_T{gate}_V",
            f"a{gate}",
            f"b{gate}",
        )
    ]
    values.extend(f"idx_Y{output}" for output in range(1, n + 1))
    values.extend(f"Y{output}_{col}" for output in range(1, n + 1) for col in range(n))
    if include_cost:
        values.append("TOTAL_COST")

    s.emit("(check-sat)")
    s.emit(f"(get-value ({' '.join(values)}))")


def build_smt(n: int, k: int, range_limit: Optional[int], cost_limit: Optional[int]) -> str:

    coefficients = coefficient_range(range_limit)
    s = SMT()
    emit_field_library(s)
    for size in range(2, n + 1):
        emit_mul(s, size)
        emit_determinant(s, size)

    emit_inputs(s, n)
    for gate in range(1, k + 1):
        emit_gate(s, n, gate, coefficients)

    previous_index: Optional[str] = None
    for output in range(1, n + 1):
        previous_index = emit_output(s, n, k, output, previous_index)

    emit_mds_constraints(s, n)
    if cost_limit is not None:
        emit_cost_constraint(s, k, cost_limit)
    emit_query(s, n, k, include_cost=cost_limit is not None)
    return s.text()


class SolutionParser:
    def __init__(self, n: int, k: int) -> None:
        self.n = n
        self.k = k

    @staticmethod
    def _bv_to_int(token: str) -> int:
        if token.startswith("#x"):
            return int(token[2:], 16)
        match = re.fullmatch(r"\(_\s+bv(\d+)\s+\d+\)", token)
        if match is None:
            raise ValueError(f"invalid bit-vector value: {token}")
        return int(match.group(1))

    def parse(self, output: str) -> str:
        status = output.split(maxsplit=1)[0] if output.strip() else ""
        if status != "sat":
            raise RuntimeError(f"Z3 returned {status or 'no output'}")

        pairs = re.findall(
            r"\(\s*([A-Za-z0-9_]+)\s+(#x[0-9A-Fa-f]+|\(_\s+bv\d+\s+\d+\))\s*\)",
            output,
        )
        if not pairs:
            raise ValueError("Z3 output does not contain model values")
        model = {name: self._bv_to_int(value) for name, value in pairs}
        return self._format(model)

    @staticmethod
    def _term(coefficient: int, node: str) -> str:
        if coefficient == 1:
            return node
        return f"L^{GF_LOG[coefficient]}*{node}"

    def _format(self, model: dict[str, int]) -> str:
        lines = ["Circuit:"]
        for gate in range(1, self.k + 1):
            nodes = candidates(self.n, gate - 1)
            left = nodes[model[f"idx_T{gate}_U"]]
            right = nodes[model[f"idx_T{gate}_V"]]
            a = model[f"a{gate}"]
            b = model[f"b{gate}"]
            lines.append(f"T{gate} = {self._term(a, left)} + {self._term(b, right)}")

        output_nodes = candidates(self.n, self.k)
        for output in range(1, self.n + 1):
            node = output_nodes[model[f"idx_Y{output}"]]
            lines.append(f"Y{output} = {node}")

        lines.append("\nMatrix:")
        for row in range(1, self.n + 1):
            values = ", ".join(f"0x{model[f'Y{row}_{col}']:x}" for col in range(self.n))
            lines.append(f"[{values}]")
        return "\n".join(lines)


def solve(
    n: int,
    k: int,
    range_limit: Optional[int],
    cost_limit: Optional[int],
    model_file: Optional[str] = None,
    result_file: Optional[str] = None,
) -> str:
    smt = build_smt(n, k, range_limit, cost_limit)
    if model_file is not None:
        Path(model_file).write_text(smt, encoding="utf-8")

    result = subprocess.run(
        ["z3", "-smt2", "-in"],
        input=smt,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"'unsat or error'")
    if result_file is not None:
        Path(result_file).write_text(result.stdout, encoding="utf-8")

    output = SolutionParser(n, k).parse(result.stdout)
    return output


def main() -> None:
    N = 4  # dimension of the MDS matrix
    K = 7  # number of gates
    RANGE_LIMIT: int | None = None  # limit for coefficient exponents (e.g., 1 means coefficients 0, +1, -1(14); None means no limit)
    COST_LIMIT: int | None = None  # maximum allowed cost for the cofficients (None means no limit)

    print(solve(N, K, RANGE_LIMIT, COST_LIMIT, model_file=SMT_FILE, result_file=RESULT_FILE))


if __name__ == "__main__":
    main()
