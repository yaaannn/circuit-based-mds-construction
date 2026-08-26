Circuit-Based MDS Matrix Construction
=====================================

Prerequisites:
--------------
You are supposed to install:

    - Python 3  (https://www.python.org/downloads/)
    - SageMath  (https://www.sagemath.org/download.html)
    - Z3        (https://github.com/Z3Prover/z3)
    - Kissat    (https://github.com/arminbiere/kissat)

File List:
----------
section_3/
    automated_construction.py       - Direct construction of MDS matrices using Z3

section_4/
    stage_1_solve_circuit.py        - Search for a circuit topology using Kissat
    stage_2_solve_coefficient.py    - Search for coefficients using Z3

result/
    check_result.py                 - Verify all result 
    mds_case_runner.py
    result_4_4.py                   - 4x4 MDS results for 4-, 8-, 16-, 32-, and 64-bit words
    result_5_5.py                   - 5x5 MDS results for 4-, 8-, 16-, 32-, and 64-bit words
    result_6_6.py                   - 6x6 MDS results for 8-, 16-, 32-, and 64-bit words
    result_7_7.py                   - 7x7 MDS results for 8-, 16-, 32-, and 64-bit words
    result_8_8.py                   - 8x8 MDS results for 8-, 16-, 32-, and 64-bit words

Usage:
------
All commands below are run from the repository root.

1. Verify all published result circuits:

       sage --python result/check_result.py

2. Run the direct construction in Section 3:

       python3 section_3/automated_construction.py

3. Search for a circuit topology in Section 4, stage 1:

       python3 section_4/stage_1_solve_circuit.py

4. Search for coefficients in Section 4, stage 2:

       sage --python section_4/stage_2_solve_coefficient.py
