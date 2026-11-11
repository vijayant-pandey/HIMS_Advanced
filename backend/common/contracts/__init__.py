"""API contracts and requirements traceability (spec 25.3, 29; HIMS-DOC-001).

* ``inventory``: every API endpoint read from the code (who may call it, scope, "confirm it's
  you", Idempotency-Key, rate limits) for the API, the app's API endpoints page and the console.
* ``reach``: what each endpoint's code can record (audit events, background events, error codes,
  outside services), found by reading the code it calls.
* ``catalog``: which requirement (backlog ticket) each API view delivers.
* ``generator``: the per-endpoint contract documents and the traceability matrix
  (``python manage.py api_contracts``; ``--check`` in CI).
"""
