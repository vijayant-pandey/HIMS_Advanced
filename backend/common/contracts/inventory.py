"""Every API endpoint, read from the code (spec 29.1, 29.5; HIMS-DOC-001).

Nothing here is written by hand: the access rule, scope, "confirm it's you", Idempotency-Key and
rate limits come from the view classes the requests actually go through, so the endpoint list in
the app, the console and the contract documents cannot drift from what the server does.
"""

import inspect
from dataclasses import dataclass, field
from functools import lru_cache

from django.conf import settings
from rest_framework import permissions as drf_permissions
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from common.permissions import FACILITY, ScopedPermission

from . import catalog

PUBLIC = "public"
SIGNED_IN = "signed_in"
PERMISSION = "permission"
ACCESS_CHOICES = (PUBLIC, SIGNED_IN, PERMISSION)

ACCESS_LABELS = {
    PUBLIC: "Anyone (no sign-in)",
    SIGNED_IN: "Anyone signed in",
    PERMISSION: "Needs a permission",
}
# Standard viewset actions and the view methods that carry them out.
_ACTION_METHODS = {
    "list": ("list", "get_queryset"),
    "retrieve": ("retrieve", "get_object", "get_queryset"),
    "create": ("create", "perform_create"),
    "update": ("update", "perform_update"),
    "partial_update": ("partial_update", "update", "perform_update"),
    "destroy": ("destroy", "perform_destroy"),
}
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass(frozen=True)
class Endpoint:
    method: str
    path: str
    view: type
    action: str
    access: str
    permission: str
    scope: str
    confirm_identity: bool
    idempotency: str  # "", "optional" or "required"
    idempotency_operation: str
    throttles: tuple[str, ...]
    requirements: tuple[str, ...]
    summary: str
    methods: tuple = field(default=(), compare=False, repr=False)

    @property
    def key(self) -> str:
        return f"{self.method} {self.path}"

    @property
    def view_name(self) -> str:
        return f"{self.view.__module__}.{self.view.__qualname__}"

    @property
    def app_label(self) -> str:
        parts = self.view.__module__.split(".")
        return parts[1] if parts[0] in {"apps", "common"} else parts[0]

    @property
    def writes(self) -> bool:
        return self.method in _WRITE_METHODS

    @property
    def needs_permission(self) -> bool:
        return self.access == PERMISSION

    @property
    def mfa(self) -> bool:
        """Privileged users must have passed two-factor (ScopedPermission; HIMS-IAM-005)."""
        return self.needs_permission


def _request(method: str, path: str):
    factory = APIRequestFactory()
    return Request(factory.generic(method, path))


def _instance(callback, method: str):
    view = callback.cls(**getattr(callback, "initkwargs", {}))
    actions = getattr(callback, "actions", None) or {}
    view.action_map = actions
    view.action = actions.get(method.lower())
    view.format_kwarg = None
    view.kwargs = {}
    view.args = ()
    view.swagger_fake_view = True
    return view


def _access(view, method: str, path: str) -> str:
    view.request = _request(method, path)
    classes = [type(item) for item in view.get_permissions()]
    if any(issubclass(cls, ScopedPermission) for cls in classes):
        return PERMISSION
    if any(issubclass(cls, drf_permissions.IsAuthenticated) for cls in classes):
        return SIGNED_IN
    return PUBLIC


def _own_methods(view_cls, names) -> tuple:
    """The view's own methods (not Django REST framework's) that run for this action."""
    found = []
    for name in names:
        member = getattr(view_cls, name, None)
        if member is None or not callable(member):
            continue
        function = inspect.unwrap(member)
        module = getattr(function, "__module__", "") or ""
        if module.startswith(("apps.", "common.")) and function not in found:
            found.append(function)
    return tuple(found)


_STANDARD = {
    "list": "List",
    "retrieve": "Open one",
    "create": "Add",
    "update": "Change",
    "partial_update": "Change",
    "destroy": "Remove",
}


def _first_paragraph(item) -> str:
    # Own docstring only: inherited ones would describe Django REST framework, not HIMS.
    text = inspect.cleandoc(getattr(item, "__doc__", None) or "")
    return " ".join(text.split("\n\n")[0].split())


def _summary(method: str, action: str, path: str, methods, view_cls) -> str:
    """The action's own docstring; for standard actions, what it does plus the view's."""
    written = catalog.PURPOSES.get(f"{method} {path}")
    if written:
        return written
    own = next((text for text in map(_first_paragraph, methods[:1]) if text), "")
    about = _first_paragraph(view_cls)
    resource = next(part for part in reversed(path.split("/")) if part and "{" not in part)
    if action in _STANDARD:
        label = f"{_STANDARD[action]} ({resource.replace('-', ' ')})"
        return f"{label}. {own or about}".strip()
    if own:
        return own
    if action == method.lower():  # a plain view: its class says what it is for
        return about
    return ""


def _throttles(view) -> tuple[str, ...]:
    """Rate-limit scopes (``anon``, ``user``, ``login``...); the rates are settings."""
    rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    found = []
    for throttle in view.get_throttles():
        scope = getattr(throttle, "scope", None) or getattr(view, "throttle_scope", None)
        if scope and scope in rates:
            found.append(scope)
    return tuple(found)


def _idempotency(methods) -> tuple[str, str]:
    for member in methods:
        marker = getattr(member, "idempotency", None)
        if marker:
            return ("required" if marker["required"] else "optional", marker["operation"])
    return "", ""


def _raw_methods(view_cls, names) -> tuple:
    """As ``_own_methods`` but without unwrapping, so decorator markers stay visible."""
    return tuple(
        getattr(view_cls, name) for name in names if callable(getattr(view_cls, name, None))
    )


@lru_cache(maxsize=1)
def endpoints() -> tuple[Endpoint, ...]:
    from drf_spectacular.generators import EndpointEnumerator

    found = []
    for path, _regex, method, callback in EndpointEnumerator().get_api_endpoints():
        if not path.startswith("/api/v1/"):
            continue  # the schema document itself
        view = _instance(callback, method)
        action = view.action or method.lower()
        names = _ACTION_METHODS.get(action, (action,))
        methods = _own_methods(callback.cls, names)
        access = _access(view, method, path)
        # Read from the view itself: some decide scope per action (a property).
        mapping = getattr(view, "required_permissions", None) or {}
        idempotency, operation = _idempotency(_raw_methods(callback.cls, names))
        found.append(
            Endpoint(
                method=method,
                path=path,
                view=callback.cls,
                action=action,
                access=access,
                permission=mapping.get(action, "") if access == PERMISSION else "",
                scope=getattr(view, "permission_scope", "organization")
                if access == PERMISSION
                else "",
                confirm_identity=action in getattr(view, "sensitive_actions", ()),
                idempotency=idempotency,
                idempotency_operation=operation,
                throttles=_throttles(view),
                requirements=catalog.requirements_for(callback.cls),
                summary=_summary(method, action, path, methods, callback.cls),
                methods=methods,
            )
        )
    return tuple(sorted(found, key=lambda item: (item.path, item.method)))


def scope_label(endpoint: Endpoint) -> str:
    if endpoint.access != PERMISSION:
        return "—"
    if endpoint.scope == FACILITY:
        return (
            "Facility or department: a grant at one facility or department is enough; rows "
            "outside it stay hidden (404)"
        )
    return "Whole hospital: the grant must cover the whole organization"
