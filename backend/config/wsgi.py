import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

from common.tracing import configure_tracing

# Before the handler loads its middleware, so API requests are traced (HIMS-PLAT-016).
configure_tracing("hims-api")

application = get_wsgi_application()
