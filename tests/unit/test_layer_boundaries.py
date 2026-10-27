"""Vrstvy backend, common a services nesmú importovať PySide6 (NFR-12)."""

import subprocess
import sys

# Kontrola beží v novom procese, lebo v tomto už PySide6 načítal plugin pytest-qt.
CHECK = """
import importlib, pkgutil, sys
for name in ("krok.backend", "krok.common", "krok.services"):
    package = importlib.import_module(name)
    for module in pkgutil.walk_packages(package.__path__, name + "."):
        if not module.name.endswith(".__main__"):
            importlib.import_module(module.name)
print(*sorted(m for m in sys.modules if m.split(".")[0] in ("PySide6", "shiboken6")))
"""


def test_non_gui_layers_do_not_import_pyside6() -> None:
    result = subprocess.run(
        [sys.executable, "-c", CHECK], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == ""
