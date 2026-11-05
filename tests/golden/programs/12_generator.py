def pocitaj(n):
    i = 0
    while i < n:
        yield i
        i += 1


def nasobic(k):
    return lambda x: x * k


stvorce = [x * x for x in pocitaj(2)]
dvakrat = nasobic(2)
print(stvorce, dvakrat(4))
