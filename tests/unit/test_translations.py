import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "update_translations.py"


def test_translations_are_complete_and_up_to_date() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        capture_output=True,
        encoding="utf-8",
        env=os.environ | {"PYTHONUTF8": "1"},
    )
    assert result.returncode == 0, result.stderr
