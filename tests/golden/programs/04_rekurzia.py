def faktorial(n):
    if n <= 1:
        return 1
    return n * faktorial(n - 1)


print(faktorial(3))
