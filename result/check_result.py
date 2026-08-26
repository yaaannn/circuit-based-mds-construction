from mds_case_runner import run_cases
from result_4_4 import CASES as result_4_4_cases
from result_5_5 import CASES as result_5_5_cases
from result_6_6 import CASES as result_6_6_cases
from result_7_7 import CASES as result_7_7_cases
from result_8_8 import CASES as result_8_8_cases

if __name__ == "__main__":
    run_cases(result_4_4_cases, matrix_order=4)
    run_cases(result_5_5_cases, matrix_order=5)
    run_cases(result_6_6_cases, matrix_order=6)
    run_cases(result_7_7_cases, matrix_order=7)
    run_cases(result_8_8_cases, matrix_order=8)
