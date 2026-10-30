"""CI supply-chain rules (spec 33.6; HIMS-PLAT-013). Reads the workflow files; runs offline."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _steps(workflow: dict):
    for name, job in workflow.get("jobs", {}).items():
        for step in job.get("steps", []):
            yield name, step


def test_workflows_exist():
    assert WORKFLOWS, "no workflow files found"


def test_every_action_is_pinned_to_a_commit_sha_with_its_release_named():
    for path in WORKFLOWS:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            match = re.match(r"^\s*-?\s*uses:\s*(\S+)(.*)$", line)
            if not match or match.group(1).startswith("./"):
                continue
            action, rest = match.groups()
            assert PINNED.match(action), f"{path.name}: pin {action} to a full commit SHA"
            assert re.search(r"#\s*v\d", rest), f"{path.name}: name the release after {action}"


def test_token_is_read_only_and_never_broader():
    for path in WORKFLOWS:
        workflow = _load(path)
        assert workflow.get("permissions") == {}, f"{path.name}: default permissions must be {{}}"
        for name, job in workflow["jobs"].items():
            granted = job.get("permissions")
            assert granted is not None, f"{path.name}:{name} must declare its permissions"
            assert all(level == "read" for level in granted.values()), f"{path.name}:{name}"


def test_no_untrusted_pull_request_code_gets_secrets():
    for path in WORKFLOWS:
        workflow = _load(path)
        triggers = workflow.get(True) or workflow.get("on")  # YAML 1.1 reads "on" as True
        assert "pull_request_target" not in (triggers or {}), path.name
        text = path.read_text(encoding="utf-8")
        used = set(re.findall(r"secrets\.([A-Z_]+)", text))
        assert used <= {"GITHUB_TOKEN"}, f"{path.name}: unexpected secrets {used}"


def test_checkouts_do_not_keep_git_credentials():
    for path in WORKFLOWS:
        for name, step in _steps(_load(path)):
            if str(step.get("uses", "")).startswith("actions/checkout@"):
                assert step.get("with", {}).get("persist-credentials") is False, f"{name}"


def test_jobs_have_time_limits():
    for path in WORKFLOWS:
        for name, job in _load(path)["jobs"].items():
            assert job.get("timeout-minutes"), f"{path.name}:{name} needs timeout-minutes"
