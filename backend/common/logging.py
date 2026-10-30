"""JSON log formatter.

Log messages must not contain PHI, credentials or raw provider payloads (spec 13.4). Pass
identifiers and sanitized outcomes through ``extra=`` rather than formatting record contents
into the message.
"""

import json
import logging
from datetime import UTC, datetime

from common.tracing import current_trace_ids

_STANDARD_ATTRS = frozenset(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Links the log line to its trace when tracing is on (HIMS-PLAT-016).
        payload.update(current_trace_ids())
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)
