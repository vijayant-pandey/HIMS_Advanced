"""Gunicorn settings for the API container (Dockerfile CMD).

Access log (spec 13.3, 27.2 "minimise sensitive data in logs and URLs"): the path only (%(U)s),
never the query string or the referring page, so search words such as a patient's name never
reach the logs. The reference number (X-Request-ID) links the line to the audit log and traces.
"""

bind = "0.0.0.0:8000"
workers = 3
accesslog = "-"
access_log_format = '%(h)s %(t)s "%(m)s %(U)s %(H)s" %(s)s %(B)s %(M)sms ref=%({x-request-id}o)s'
