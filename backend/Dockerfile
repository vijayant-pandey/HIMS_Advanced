# Backend image: built once per commit and promoted unchanged through
# Development -> QA -> Staging -> Production (spec 31.5, 33.3).
#
# One image, several roles (selected by the ECS task definition command):
#   API:        gunicorn config.wsgi:application --config config/gunicorn_conf.py
#   Worker:     celery -A config worker -Q <deployment>.default,<deployment>.outbox
#   Beat:       celery -A config beat
#   Dispatcher: python manage.py run_outbox_dispatcher
#   Migrations: python manage.py migrate   (dedicated release job, never on API start-up)

FROM python:3.13-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY requirements/ requirements/
# Hash-locked (HIMS-PLAT-012): every package, including indirect ones, must match a reviewed
# checksum in base.txt, and nothing outside the lockfile is installed.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --require-hashes --no-deps -r requirements/base.txt

FROM python:3.13-slim AS runtime
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production
RUN groupadd --system hims && useradd --system --gid hims --home /app hims
COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY --chown=hims:hims . .
USER hims
EXPOSE 8000
# Bind address, workers and a PHI-safe access log (no query strings) are in config/gunicorn_conf.py.
CMD ["gunicorn", "config.wsgi:application", "--config", "config/gunicorn_conf.py"]
