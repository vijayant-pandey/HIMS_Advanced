"""Gunicorn settings for the API container (Dockerfile CMD).

Access log (spec 13.3, 27.2 "minimise sensitive data in logs and URLs"): the path only (%(U)s),
never the query string or the referring page, so search words such as a patient's name never
reach the logs. The reference number (X-Request-ID) links the line to the audit log and traces.

Hosts set the port and the size (HIMS-OPS-024): ``PORT`` is the port the host sends traffic to
(Render gives one; 8000 otherwise) and ``WEB_CONCURRENCY`` the number of worker processes (3 by
default; 2 on a free plan with 512 MB of memory). ``GUNICORN_TIMEOUT`` (120 s) leaves room for the
scheduled jobs started over HTTPS on a slow free CPU (common/outbox/trigger.py).
"""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", "3"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
accesslog = "-"
access_log_format = '%(h)s %(t)s "%(m)s %(U)s %(H)s" %(s)s %(B)s %(M)sms ref=%({x-request-id}o)s'
