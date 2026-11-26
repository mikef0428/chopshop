"""The project was renamed to Chop Shop; the old name must not creep back in."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD_NAME = "auto" + "clip"
#: Planning records written before the rename; they describe the old layout.
HISTORICAL = "docs/superpowers/"


def test_old_name_is_gone():
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    offenders = []
    for name in tracked:
        if name.startswith(HISTORICAL):
            continue
        if OLD_NAME in name.lower():
            offenders.append(name)
            continue
        try:
            text = (ROOT / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        if OLD_NAME in text.lower():
            offenders.append(name)
    assert not offenders, f"old project name found in: {offenders}"
