import pytest
from django.db import transaction
from django.test import override_settings

from common.outbox import registry
from common.outbox.dispatcher import dispatch_pending, process_event
from common.outbox.models import OutboxEvent, ProcessedEvent
from common.outbox.services import OutboxUsageError, publish_event


def _publish(**overrides):
    params = {
        "event_type": "test.thing.happened",
        "aggregate_type": "thing",
        "aggregate_id": "thing-1",
        "payload": {"thing_id": "thing-1"},
    }
    params.update(overrides)
    with transaction.atomic():
        return publish_event(**params)


@pytest.mark.django_db(transaction=True)
def test_publish_outside_transaction_is_rejected():
    with pytest.raises(OutboxUsageError):
        publish_event(event_type="x", aggregate_type="y", aggregate_id="z", payload={})


@pytest.mark.django_db
def test_event_rolls_back_with_business_transaction():
    with pytest.raises(RuntimeError), transaction.atomic():
        publish_event(event_type="x", aggregate_type="y", aggregate_id="z", payload={})
        raise RuntimeError("business write failed")
    assert not OutboxEvent.objects.exists()


@pytest.mark.django_db
def test_envelope_matches_spec_shape():
    event = _publish()
    envelope = event.envelope()
    assert set(envelope) == {
        "event_id",
        "event_type",
        "event_version",
        "occurred_at",
        "customer_id",
        "facility_id",
        "aggregate_type",
        "aggregate_id",
        "correlation_id",
        "causation_id",
        "payload",
    }
    assert envelope["customer_id"] == "test-deployment"


@pytest.mark.django_db
def test_dispatch_marks_events_published():
    event = _publish()
    published = []
    assert dispatch_pending(publish=published.append) == 1
    event.refresh_from_db()
    assert event.status == OutboxEvent.Status.PUBLISHED
    assert published == [event]
    assert dispatch_pending(publish=published.append) == 0


@pytest.mark.django_db
@override_settings(HIMS_OUTBOX_MAX_ATTEMPTS=2)
def test_publish_failures_back_off_then_dead_letter():
    event = _publish()

    def broken(_event):
        raise ConnectionError("broker down")

    dispatch_pending(publish=broken)
    event.refresh_from_db()
    assert event.status == OutboxEvent.Status.PENDING
    assert event.attempts == 1
    assert event.last_error == "ConnectionError"

    OutboxEvent.objects.filter(pk=event.pk).update(available_at=event.occurred_at)
    dispatch_pending(publish=broken)
    event.refresh_from_db()
    assert event.status == OutboxEvent.Status.DEAD


@pytest.mark.django_db
def test_handlers_run_once_per_event_even_when_redelivered():
    calls = []

    @registry.event_handler("test.dedupe")
    def handler(event):
        calls.append(event.id)

    event = _publish(event_type="test.dedupe")
    process_event(event.id)
    process_event(event.id)  # at-least-once redelivery

    assert calls == [event.id]
    assert ProcessedEvent.objects.filter(event_id=event.id).count() == 1


@pytest.mark.django_db
def test_failed_handler_can_retry():
    attempts = []

    @registry.event_handler("test.retry")
    def flaky(event):
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionError("downstream unavailable")

    event = _publish(event_type="test.retry")
    with pytest.raises(ConnectionError):
        process_event(event.id)
    process_event(event.id)
    assert len(attempts) == 2
    assert ProcessedEvent.objects.filter(event_id=event.id).count() == 1
