"""Optimistic concurrency for resources where stale writes are dangerous (spec 29.3)."""

from django.db import models

from common.exceptions import StaleResourceError


def lock_for_update(model: type[models.Model], *, pk, expected_version: int | None):
    """Lock the row and verify the caller edited the current version.

    Must be called inside ``transaction.atomic``. Returns the locked instance; the caller
    applies changes and calls ``bump_version`` before saving.
    """
    instance = model.objects.select_for_update().get(pk=pk)
    if expected_version is None or instance.version != expected_version:
        raise StaleResourceError(
            "This record changed since you loaded it. Reload and re-apply your changes."
        )
    return instance


def bump_version(instance) -> None:
    instance.version += 1
