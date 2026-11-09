"""Settings used only while building the server image, to collect the static files
(``collectstatic``; HIMS-OPS-010). Collecting needs no database and no secrets, so harmless
placeholders are set here; the image never runs with these settings (it runs with production).
"""

import os

os.environ.setdefault("HIMS_ENV_FILE", "__no_env_file_at_build__")
os.environ.setdefault("HIMS_ENVIRONMENT", "local")
os.environ.setdefault("HIMS_DEPLOYMENT_ID", "image-build")
# A meaningless placeholder: collecting files never signs anything.
os.environ.setdefault("DJANGO_SECRET_KEY", "x" * 50)
os.environ.setdefault("DATABASE_URL", "postgres://image-build@localhost:5432/image-build")

from .base import *  # noqa: F403
from .base import HOSTED_STORAGES

DEBUG = False
STORAGES = HOSTED_STORAGES  # the same fingerprinted files production serves
