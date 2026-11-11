# The hosted image: the screens (React app) and the server in one image, served from one address
# (HIMS-OPS-022; ADR-034). Built from the repository root:
#
#   docker build -t hims .
#
# Roles, selected by the command (the default runs the web server):
#   Web:            gunicorn config.wsgi:application --config config/gunicorn_conf.py
#   Scheduled jobs: python manage.py run_scheduled_jobs   (a host timer every minute; HIMS-OPS-023)
#   Migrations:     python manage.py migrate               (a release step, never on web start-up)
#   Worker / beat:  celery -A config worker / beat        (only where a broker is available)
#
# backend/Dockerfile builds the server alone (no screens) and is kept for that use.

FROM node:24.18.0-slim AS screens
WORKDIR /screens
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Type check and build, exactly as CI does (`npm run build`); the result is in /screens/dist.
RUN npm run build

FROM python:3.13-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY backend/requirements/ requirements/
# Hash-locked (HIMS-PLAT-012): every package must match a reviewed checksum in base.txt.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --require-hashes --no-deps -r requirements/base.txt

FROM python:3.13-slim AS runtime
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    HIMS_FRONTEND_DIST=/app/screens
RUN groupadd --system hims && useradd --system --gid hims --home /app hims
COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY --chown=hims:hims backend/ .
COPY --from=screens --chown=hims:hims /screens/dist /app/screens
# Admin console and API docs files, collected once at build time and served by WhiteNoise
# (HIMS-OPS-010). Needs no database or secrets (config/settings/build.py).
RUN DJANGO_SETTINGS_MODULE=config.settings.build python manage.py collectstatic --noinput -v 0
USER hims
EXPOSE 8000
# Bind address, workers and a PHI-safe access log (no query strings) are in config/gunicorn_conf.py.
CMD ["gunicorn", "config.wsgi:application", "--config", "config/gunicorn_conf.py"]
