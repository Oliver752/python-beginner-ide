import os

# GUI testy bežia bez zobrazovania okien. Musí sa nastaviť pred vytvorením QApplication.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
