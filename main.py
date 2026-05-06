def multiply_matrices(matrix_a, matrix_b):
    if not matrix_a or not matrix_b:
        raise ValueError('Matrices must not be empty')

    a_columns = len(matrix_a[0])
    b_columns = len(matrix_b[0])

    if any(len(row) != a_columns for row in matrix_a):
        raise ValueError('First matrix must be rectangular')
    if any(len(row) != b_columns for row in matrix_b):
        raise ValueError('Second matrix must be rectangular')
    if a_columns != len(matrix_b):
        raise ValueError('Number of columns in first matrix must match rows in second matrix')

    return [
        [
            sum(matrix_a[row][i] * matrix_b[i][column] for i in range(a_columns))
            for column in range(b_columns)
        ]
        for row in range(len(matrix_a))
    ]


def main():
    print('Hello, world!')


if __name__ == '__main__':
    main()
