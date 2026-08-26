from mds_case_runner import C4, C8, C16, C32, C64, E4, E8, E16, E32, E64

CASES = [
    {
        "name": "4*4 MDS",
        "dimensions": [4, 8, 16, 32, 64],
        "circuit": """
            t1 = x3 + x4
            t2 = x1 + x2
            t3 = x3 + t2
            t4 = t1 + t3    (y1)
            t5 = x1 + t1    
            t6 = t2 + t5    (y2)
            t7 = t4 + t5    (y3)
            t8 = t3 + t6    (y4)
""",
        "exp_a": [0, 0, 0, -1, 0, 0, 0, 0],
        "exp_b": [0, 0, 1, 0, 0, 1, 0, 0],
        "binary_matrix_positions": {
            # x^4 + x + 1
            4: C4 + E4(2, 4),
            # x^8 + x^2 + 1
            8: C8 + E8(3, 8),
            # x^16 + x^4 +x 1
            16: C16 + E16(5, 16),
            # x^32 + x^8 + 1
            32: C32 + E32(9, 32),
            # x^64 + x^16 + 1
            64: C64 + E64(17, 64),
        },
    },
]
