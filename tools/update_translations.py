"""Aktualizuje preklady rozhrania (Qt Linguist).

    python tools/update_translations.py           # lupdate (kód -> .ts) a lrelease (.ts -> .qm)
    python tools/update_translations.py --check   # iba overí, že preklady sú aktuálne a úplné

Pri novom reťazci: spustiť skript, doplniť preklad v súbore .ts (pyside6-linguist
alebo ručne) a spustiť skript znova.
"""

import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "krok"
TRANSLATIONS = PACKAGE / "translations"
SOURCE_LANGUAGE = "en"
TARGET_LANGUAGES = ("sk",)


def tool(name: str) -> str:
    # Nástroje PySide6 ležia vedľa interpretera, takže venv netreba aktivovať.
    path = shutil.which(name, path=str(Path(sys.executable).parent))
    if path is None:
        raise SystemExit(f"{name} sa nenašiel vedľa {sys.executable}")
    return path


def update(ts: Path, qm: Path, language: str, silent: bool) -> None:
    quiet = ["-silent"] if silent else []
    sources = sorted(str(path) for path in PACKAGE.rglob("*.py"))
    subprocess.run(
        [tool("pyside6-lupdate"), *quiet, *sources, "-no-obsolete", "-locations", "none",
         "-source-language", SOURCE_LANGUAGE, "-target-language", language, "-ts", str(ts)],
        check=True,
    )  # fmt: skip
    subprocess.run([tool("pyside6-lrelease"), *quiet, str(ts), "-qm", str(qm)], check=True)


def untranslated(ts: Path) -> list[str]:
    missing = []
    for message in ET.parse(ts).getroot().iter("message"):
        translation = message.find("translation")
        if translation is None or translation.get("type") == "unfinished" or not translation.text:
            missing.append(message.findtext("source", ""))
    return missing


def same_text(a: Path, b: Path) -> bool:
    return a.read_text(encoding="utf-8").splitlines() == b.read_text(encoding="utf-8").splitlines()


def main(argv: list[str]) -> int:
    check = argv == ["--check"]
    problems = []
    for language in TARGET_LANGUAGES:
        ts = TRANSLATIONS / f"krok_{language}.ts"
        qm = ts.with_suffix(".qm")
        if check:
            with tempfile.TemporaryDirectory() as tmp:
                fresh_ts, fresh_qm = Path(tmp) / ts.name, Path(tmp) / qm.name
                shutil.copyfile(ts, fresh_ts)
                update(fresh_ts, fresh_qm, language, silent=True)
                if not same_text(ts, fresh_ts):
                    problems.append(f"{ts.name}: nezodpovedá kódu, spustite skript bez --check")
                if not qm.exists() or qm.read_bytes() != fresh_qm.read_bytes():
                    problems.append(f"{qm.name}: nie je aktuálny, spustite skript bez --check")
        else:
            update(ts, qm, language, silent=False)
        problems += [f"{ts.name}: chýba preklad pre {source!r}" for source in untranslated(ts)]
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
