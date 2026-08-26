from mds_case_runner import C4, C8, C16, C32, C64, E4, E8, E16, E32, E64

CASES = [
    {
        "name": "6*6 MDS",
        "dimensions": [8, 16, 32, 64],
        "circuit": """
            t1 = x1 + x2                      
            t2 = x1 + x5                      
            t3 = x4 + t1                      
            t4 = x6 + t3                      
            t5 = x3 + x6                      
            t6 = t1 + t5                      
            t7 = t2 + t4                      
            t8 = t3 + t7                      
            t9 = t6 + t8            (y1)      
            t10 = x5 + t6                     
            t11 = t1 + t10                    
            t12 = t4 + t11          (y2)      
            t13 = t7 + t10          (y3)      
            t14 = x3 + t7           (y4)      
            t15 = t8 + t12          (y5)      
            t16 = t9 + t11          (y6)
""",
        "exp_a": [-1, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0],
        "exp_b": [0, 0, 0, -1, 0, 0, 0, -1, 0, 2, 1, 1, 0, 0, 0, 0],
        "binary_matrix_positions": {
            8: C8 + E8(2, 2) + E8(3, 8),
            16: C16 + E16(1, 2) + E16(3, 5),
            32: C32 + E32(1, 11),
            64: C64 + E64(1, 13),
        },
    },
]
