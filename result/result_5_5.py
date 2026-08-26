from mds_case_runner import C4, C8, C16, C32, C64, E4, E8, E16, E32, E64

CASES = [
    {
        "name": "5*5 MDS 1",
        "dimensions": [4],
        "circuit": """
            t1 = x1 + x4
            t2 = x2 + t1
            t3 = x5 + t2
            t4 = x1 + t3
            t5 = x4 + t3
            t6 = x3 + t4    (y1)
            t7 = x3 + t5
            t8 = t5 + t6
            t9 = x5 + t1
            t10 = t2 + t7   (y2)
            t11 = t8 + t10  (y3)
            t12 = t8 + t9   (y4)
            t13 = t7 + t12  (y5)
""",
        "exp_a": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -1, 0],
        "exp_b": [0, 0, 0, -2, 0, 0, 0, 0, 0, 1, 0, 0, 0],
        "binary_matrix_positions": {
            4: C4 + E4(2, 4),
        },
    },
    {
        "name": "5*5 MDS 2",
        "dimensions": [8, 16, 32, 64],
        "circuit": """
            t1 = x1 + x2
            t2 = x5 + t1
            t3 = x4 + t1
            t4 = x3 + t2
            t5 = x2 + t4
            t6 = x3 + t3
            t7 = x4 + t5
            t8 = t6 + t7    (y1)
            t9 = t4 + t8    (y2)
            t10 = x5 + t7   (y3)
            t11 = t2 + t6   (y4)
            t12 = t3 + t5   (y5)
""",
        "exp_a": [0, 0, 0, 0, 0, 0, 0, -1, 0, 0, 0, 0],
        "exp_b": [0, 0, -1, 1, 1, 0, 1, 0, 0, 0, 0, 0],
        "binary_matrix_positions": {
            8: C8 + E8(2, 2) + E8(3, 8),
            16: C16 + E16(1, 1),
            32: C32 + E32(1, 2),
            64: C64 + E64(1, 4),
        },
    },
]
