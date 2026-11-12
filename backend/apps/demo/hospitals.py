"""The ten demo hospitals (HIMS-QA-004), from ``hospitals.json`` (also read by the launcher)."""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

FILE = Path(__file__).with_name("hospitals.json")


@dataclass(frozen=True)
class Hospital:
    key: str
    country: str
    display_name: str
    legal_name: str
    timezone: str
    currency: str
    backend_port: int
    frontend_port: int
    branches: tuple[dict, ...]

    @property
    def deployment_id(self) -> str:
        return f"demo-{self.key}"

    @property
    def database(self) -> str:
        return f"hims_demo_{self.key.replace('-', '_')}"

    @property
    def env_file(self) -> str:
        return f".env.demo-{self.key}"

    @property
    def admin_email(self) -> str:
        return f"admin@{self.key}.demo.test"

    @property
    def auditor_email(self) -> str:
        return f"auditor@{self.key}.demo.test"


@lru_cache(maxsize=1)
def all_hospitals() -> tuple[Hospital, ...]:
    data = json.loads(FILE.read_text(encoding="utf-8"))
    return tuple(
        Hospital(**{**row, "branches": tuple(row["branches"])}) for row in data["hospitals"]
    )


def by_key(key: str) -> Hospital:
    for hospital in all_hospitals():
        if hospital.key == key:
            return hospital
    known = ", ".join(h.key for h in all_hospitals())
    raise KeyError(f"No demo hospital '{key}'. Known: {known}.")
