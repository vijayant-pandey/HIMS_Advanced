"""The hash-locked lockfiles match the dependencies we ask for (HIMS-PLAT-012, spec 33).

Runs offline. If this fails, regenerate the lockfiles as described in
docs/workflows/dependencies.md instead of editing base.txt/dev.txt by hand.
"""

import re
from pathlib import Path

REQUIREMENTS = Path(__file__).resolve().parents[2] / "requirements"
PIN = re.compile(r"^([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?==([^\s;\\]+)")


def _pins(path: Path) -> dict[str, str]:
    pins = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = PIN.match(line.strip())
        if match:
            pins[match.group(1).lower().replace("_", "-")] = match.group(2)
    return pins


def _locked_entries(path: Path) -> list[str]:
    """Each package entry of a lockfile with its continuation lines joined."""
    text = path.read_text(encoding="utf-8").replace("\\\n", " ")
    return [line for line in text.splitlines() if PIN.match(line.strip())]


def test_every_requested_package_is_locked_at_the_same_version():
    for name in ("base", "dev"):
        wanted = _pins(REQUIREMENTS / f"{name}.in")
        locked = _pins(REQUIREMENTS / f"{name}.txt")
        different = {
            package: (version, locked.get(package))
            for package, version in wanted.items()
            if locked.get(package) != version
        }
        assert different == {}, f"Regenerate requirements/{name}.txt: {different}"


def test_every_locked_package_has_a_checksum():
    for name in ("base", "dev"):
        missing = [
            entry.split()[0]
            for entry in _locked_entries(REQUIREMENTS / f"{name}.txt")
            if "--hash=sha256:" not in entry
        ]
        assert missing == [], f"{name}.txt entries without hashes: {missing}"


def test_dev_tools_use_exactly_the_production_versions():
    base = _pins(REQUIREMENTS / "base.txt")
    dev = _pins(REQUIREMENTS / "dev.txt")
    different = {p: (v, dev[p]) for p, v in base.items() if p in dev and dev[p] != v}
    assert different == {}, f"dev.txt differs from base.txt: {different}"
    assert set(base) <= set(dev), f"Missing from dev.txt: {sorted(set(base) - set(dev))}"
