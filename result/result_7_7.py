from mds_case_runner import C4, C8, C16, C32, C64, E4, E8, E16, E32, E64

CASES = [
    {
        "name": "7*7 MDS",
        "dimensions": [8, 16, 32, 64],
        "circuit": """
            t1 = x1 + x2                      
            t2 = x4 + x6                      
            t3 = x3 + t2                      
            t4 = x7 + t3                      
            t5 = x5 + t3                      
            t6 = x6 + t5                      
            t7 = t1 + t6                      
            t8 = t4 + t7            (y1)      
            t9 = x3 + t1                      
            t10 = t5 + t8                     
            t11 = x1 + t4                     
            t12 = t9 + t11                    
            t13 = x5 + t11                    
            t14 = t10 + t12         (y2)      
            t15 = t2 + t13                    
            t16 = t13 + t14         (y3)      
            t17 = t7 + t15          (y4)      
            t18 = t10 + t15                   
            t19 = t6 + t18          (y5)      
            t20 = t12 + t17         (y6)      
            t21 = t9 + t18          (y7) 
""",
        "exp_a": [0, 0, 0, 0, -1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        "exp_b": [0, 0, 0, 0, 3, 0, 0, 0, 3, 0, -2, -3, 0, -1, 0, 0, 1, -2, 0, 0, 0],
        "target": {"cost": [8]},
        "binary_matrix_positions": {
            8: C8 + E8(2, 2) + E8(3, 8),
            16: C16 + E16(1, 2) + E16(3, 5),
            32: C32 + E32(1, 11),
            64: C64 + E64(1, 15),
        },
    },
]
