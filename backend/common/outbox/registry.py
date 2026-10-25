"""Registry of outbox event handlers.

Handlers live in each domain's ``event_handlers.py``::

    @event_handler("staff.member.created")
    def send_staff_invitation(event: OutboxEvent) -> None: ...

A handler runs inside a transaction together with its deduplication marker, so its database
effects happen at most once per event. External side effects (email, payer APIs) must
themselves be idempotent or reconcilable, because a crash after the call but before commit
causes a retry (spec 14.3).
"""

from collections import defaultdict
from collections.abc import Callable

_handlers: dict[str, list[tuple[str, Callable]]] = defaultdict(list)


def event_handler(event_type: str):
    def decorator(func: Callable) -> Callable:
        name = f"{func.__module__}.{func.__qualname__}"
        if all(existing != name for existing, _ in _handlers[event_type]):
            _handlers[event_type].append((name, func))
        return func

    return decorator


def handlers_for(event_type: str) -> list[tuple[str, Callable]]:
    return list(_handlers.get(event_type, ()))
