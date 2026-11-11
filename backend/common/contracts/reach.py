"""What an endpoint's code can do, found by reading the code it calls (spec 29.5; HIMS-DOC-001).

Starting from the view's own methods (and, for create and update, its serializer), every function
and class called from HIMS code is followed a few steps deep. Along the way it collects:

* audit events (``AuditAction.X``), background events (``publish_event(event_type=...)``);
* error codes (``code="..."`` and the ``code`` of each HIMS error class raised);
* database locks and transactions; outside services (messages, virus scanner, PostgreSQL tools).

It lists what the code *can* do on any path, not what one request does; a test pins the audit
events of the most important writes, so a broken walk fails CI instead of going quiet.
"""

import importlib
import inspect
import re
from dataclasses import dataclass
from functools import cache

from apps.audit.services import AuditAction
from common.exceptions import DomainError

_AUDIT = re.compile(r"AuditAction\.([A-Z][A-Z0-9_]+)")
_EVENT = re.compile(r"event_type\s*=\s*[\"']([a-z0-9_.]+)[\"']")
_CODE = re.compile(r"\bcode\s*=\s*[\"']([A-Z][A-Z0-9_]+)[\"']")
_RAISE = re.compile(r"raise\s+([A-Za-z_][\w.]*)\(")
_CALL = re.compile(r"(?<![\w.\"'])((?:[A-Za-z_]\w*)(?:\.[A-Za-z_]\w*)*)\s*\(")
_DEPTH = 6
_IMPORT = re.compile(r"^\s+from\s+([\w.]+)\s+import\s+\(?([\w\s,]+?)\)?\s*$", re.M)
# Calls that only record or check (their own source would add every event in the catalog).
_STOP = {
    "apps.audit.services.record_audit_event",
    "common.outbox.services.publish_event",
    "apps.access_control.selectors.has_permission",
    "apps.access_control.selectors.get_permission_scope",
    "common.permissions.filter_by_facility_scope",
}
# Outside services, by the module the code reaches.
EXTERNAL = {
    "apps.notifications": "Messages (email; SMS printed on the console until a gateway is chosen): "
    "tried at once and logged; a failure never undoes the action",
    "common.virus_scan": "Virus scanner (ClamAV over a local socket; fails closed: "
    "SCANNER_UNAVAILABLE)",
    "apps.recovery.pg_tools": "PostgreSQL tools (pg_dump / pg_restore) on the database server",
    "apps.identity.passkeys": "Passkey checks (WebAuthn) done on the server; no outside service",
}


@dataclass(frozen=True)
class Reach:
    audit_actions: tuple[str, ...]
    events: tuple[str, ...]
    error_codes: tuple[str, ...]
    statuses: tuple[tuple[str, int], ...]  # HTTP status of each code, where the code shows it
    external: tuple[str, ...]
    transaction: bool
    row_lock: bool


def _source(item) -> str:
    try:
        return inspect.getsource(item)
    except (OSError, TypeError):
        return ""


def _ours(item) -> bool:
    module = getattr(item, "__module__", "") or ""
    return module.startswith(("apps.", "common.")) and not module.startswith("common.contracts")


def _qualified(item) -> str:
    return f"{getattr(item, '__module__', '')}.{getattr(item, '__qualname__', '')}"


def _resolve(name: str, namespace: dict, owner):
    parts = name.split(".")
    if parts[0] in {"self", "cls"}:
        if owner is None or len(parts) < 2:
            return None
        target = getattr(owner, parts[1], None)
        parts = parts[2:]
    elif parts[0] == "super":
        return None
    else:
        target = namespace.get(parts[0])
        parts = parts[1:]
    for part in parts:
        if target is None:
            return None
        target = getattr(target, part, None)
    return target


def _owner_of(function, start_owner):
    """The class a method belongs to, so ``self.x()`` resolves inside it."""
    qualname = getattr(function, "__qualname__", "")
    if "." not in qualname:
        return start_owner
    module = inspect.getmodule(function)
    owner = getattr(module, qualname.split(".")[0], None)
    return owner if inspect.isclass(owner) else start_owner


def _raised_statuses(text: str, namespace: dict) -> dict[str, int]:
    """``raise ConflictError("...", code="X")``: X gets the status of the class raised."""
    found = {}
    for match in _CODE.finditer(text):
        raised = _RAISE.findall(text, 0, match.start())
        if not raised:
            continue
        target = _resolve(raised[-1], namespace, None)
        if inspect.isclass(target) and issubclass(target, DomainError):
            found.setdefault(match.group(1), target.status_code)
    return found


def _local_imports(text: str) -> dict:
    """Names imported inside the function (common here, to avoid import cycles)."""
    found = {}
    for module_name, names in _IMPORT.findall(text):
        if not module_name.startswith(("apps", "common")):
            continue
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        for item in names.split(","):
            parts = item.split()
            if not parts:
                continue
            name, alias = parts[0], parts[-1]
            value = getattr(module, name, None)
            if value is None:
                try:
                    value = importlib.import_module(f"{module_name}.{name}")
                except ImportError:
                    continue
            found[alias] = value
    return found


def walk(starts, owner=None) -> Reach:
    audit, events, codes, external = set(), set(), set(), set()
    statuses = {}
    transaction = row_lock = False
    seen = set()
    queue = [(inspect.unwrap(item), owner, 0) for item in starts]
    while queue:
        item, current_owner, depth = queue.pop()
        key = _qualified(item)
        if key in seen or key in _STOP:
            continue
        seen.add(key)
        module = getattr(item, "__module__", "") or ""
        for prefix, label in EXTERNAL.items():
            if module.startswith(prefix):
                external.add(label)
        if inspect.isclass(item):
            if issubclass(item, DomainError):
                codes.add(item.code)
                statuses.setdefault(item.code, item.status_code)
            continue
        text = _source(item)
        audit.update(_AUDIT.findall(text))
        events.update(_EVENT.findall(text))
        codes.update(_CODE.findall(text))
        for code, status in _raised_statuses(text, getattr(item, "__globals__", {})).items():
            statuses.setdefault(code, status)
        if "transaction.atomic" in text or "@idempotent" in text:
            transaction = True
        if "select_for_update" in text or "lock_for_update" in text:
            row_lock = True
        if depth >= _DEPTH:
            continue
        namespace = {**getattr(item, "__globals__", {}), **_local_imports(text)}
        method_owner = _owner_of(item, current_owner)
        for name in set(_CALL.findall(text)):
            target = _resolve(name, namespace, method_owner)
            if target is None or not _ours(target):
                continue
            if inspect.isclass(target) or inspect.isfunction(target) or inspect.ismethod(target):
                queue.append((inspect.unwrap(target), method_owner, depth + 1))
    actions = sorted({getattr(AuditAction, name, "") for name in audit} - {""})
    return Reach(
        audit_actions=tuple(actions),
        events=tuple(sorted(events)),
        error_codes=tuple(sorted(codes)),
        statuses=tuple(
            sorted((code, status) for code, status in statuses.items() if code in codes)
        ),
        external=tuple(sorted(external)),
        transaction=transaction,
        row_lock=row_lock,
    )


def _serializer_methods(endpoint) -> list:
    if endpoint.action not in {"create", "update", "partial_update"}:
        return []
    serializer = getattr(endpoint.view, "serializer_class", None)
    if serializer is None:
        return []
    names = ("create", "update", "save", "validate")
    found = []
    for klass in serializer.__mro__:
        if not _ours(klass):
            continue
        for name, member in vars(klass).items():
            if name in names or name.startswith("validate_"):
                found.append(member)
    return found


@cache
def for_endpoint(endpoint) -> Reach:
    return walk([*endpoint.methods, *_serializer_methods(endpoint)], owner=endpoint.view)
