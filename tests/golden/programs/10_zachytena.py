def del_nulou(a):
    try:
        return a / 0
    finally:
        print("cleanup")


try:
    del_nulou(1)
except ZeroDivisionError as chyba:
    print("chyba:", chyba)
print("koniec")
