def vnutorna(zoznam):
    return zoznam[5]


def vonkajsia():
    cisla = [1, 2]
    return vnutorna(cisla)


print("pred chybou")
vonkajsia()
print("sem sa nedostane")
