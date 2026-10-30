"""Artifact A data dictionary stays complete and in step with the code (spec 28; HIMS-DATA-001)."""

import re

from django.apps import apps
from django.db.models import F, Q

from common.datadict import catalog, generator


def _columns():
    for _, models in generator.domain_models():
        for model in models:
            for field in model._meta.concrete_fields:
                yield model._meta.db_table, field


def test_committed_dictionary_and_erd_match_the_models():
    for path, text in generator.outputs().items():
        committed = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        assert committed == text, (
            f"{path.name} is out of date. Run `python manage.py data_dictionary` and commit it."
        )


def test_every_app_with_tables_belongs_to_a_documented_domain():
    with_tables = {
        config.label
        for config in apps.get_app_configs()
        if config.name.startswith(("apps.", "common."))
        and any(not m._meta.proxy for m in config.get_models())
    }
    assert with_tables <= set(catalog.DOMAINS), (
        f"Add to common/datadict/catalog.py DOMAINS: {sorted(with_tables - set(catalog.DOMAINS))}"
    )


def test_every_table_has_a_lifecycle_rule_and_none_is_stale():
    tables = generator.hims_tables()
    missing = sorted(tables - set(catalog.LIFECYCLE))
    assert missing == [], f"Add lifecycle/retention rules to catalog.LIFECYCLE: {missing}"
    assert set(catalog.LIFECYCLE) <= tables, sorted(set(catalog.LIFECYCLE) - tables)


def test_overrides_point_at_real_columns():
    real = {f"{table}.{field.column}" for table, field in _columns()}
    assert set(catalog.COLUMN_OVERRIDES) <= real, sorted(set(catalog.COLUMN_OVERRIDES) - real)


def test_credentials_are_classified_secret_and_people_data_restricted():
    secret_names = re.compile(r"password|secret|token|session_key|code_hash")
    personal_names = re.compile(r"email|display_name|given_name|family_name|ip_address")
    for table, field in _columns():
        level, _ = generator.classify(table, field)
        if secret_names.search(field.column) and not field.column.endswith("_at"):
            assert level == catalog.SECRET, f"{table}.{field.column} must be Secret"
        if personal_names.search(field.column):
            assert level == catalog.RESTRICTED, f"{table}.{field.column} must be Restricted"


def test_conditions_are_written_in_plain_words():
    condition = Q(valid_until__isnull=True) | Q(valid_until__gt=F("valid_from"))
    assert generator.format_q(condition) == "(valid_until is empty OR valid_until > valid_from)"
    assert generator.format_q(~Q(delegator=F("delegate"))) == "NOT delegator = delegate"
