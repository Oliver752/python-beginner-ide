class Zviera:
    pocet = 0

    def __init__(self, meno):
        self.meno = meno
        Zviera.pocet += 1


class Pes(Zviera):
    def __repr__(self):
        raise ValueError("chybny repr")

    def zvuk(self):
        return "haf"


rex = Pes("Rex")
print(rex.zvuk())
