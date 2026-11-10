"""Structured logging: one JSON object per line on stdout, shipped to Fluentd.

- stdout keeps working everywhere (platform log viewers, ``docker logs``);
- when ``FIHI_FLUENTD_URL`` is set, records are also POSTed in batches to
  Fluentd's ``in_http`` input by a background thread. The queue is bounded
  and a failing collector only drops log lines: it never slows a request.
"""

import json
import logging
import queue
import sys
import threading
import time
import urllib.error
import urllib.request

from . import config

_RESERVED = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record):
        doc = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
            "service": "backend",
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                doc[key] = value
        if record.exc_info:
            doc["exc"] = self.formatException(record.exc_info)
        return json.dumps(doc, ensure_ascii=False, default=str)


class FluentdHandler(logging.Handler):
    """Batches formatted records to Fluentd ``in_http`` (JSON array body)."""

    def __init__(self, url, tag, max_queue=5000, batch=200, interval=1.0):
        super().__init__()
        self._url = f"{url}/{tag}"
        self._queue = queue.Queue(maxsize=max_queue)
        self._batch = batch
        self._interval = interval
        threading.Thread(target=self._run, name="fluentd-shipper", daemon=True).start()

    def emit(self, record):
        try:
            self._queue.put_nowait(self.format(record))
        except queue.Full:
            pass  # collector down for long: drop rather than block requests

    def _run(self):
        while True:
            lines = [self._queue.get()]
            deadline = time.monotonic() + self._interval
            while len(lines) < self._batch:
                timeout = deadline - time.monotonic()
                if timeout <= 0:
                    break
                try:
                    lines.append(self._queue.get(timeout=timeout))
                except queue.Empty:
                    break
            self._send(lines)

    def _send(self, lines):
        body = ("[" + ",".join(lines) + "]").encode("utf-8")
        req = urllib.request.Request(  # noqa: S310 - URL from configuration
            self._url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=5):  # noqa: S310  # nosec B310
                    return
            except (urllib.error.URLError, OSError):
                time.sleep(0.5 * (attempt + 1))


_configured = False


def setup():
    global _configured
    if _configured:
        return
    _configured = True
    root = logging.getLogger("fihi")
    root.setLevel(config.LOG_LEVEL)
    root.propagate = False
    formatter = JsonFormatter()
    out = logging.StreamHandler(sys.stdout)
    out.setFormatter(formatter)
    root.addHandler(out)
    if config.FLUENTD_URL:
        shipper = FluentdHandler(config.FLUENTD_URL, config.FLUENTD_TAG)
        shipper.setFormatter(formatter)
        root.addHandler(shipper)


def get(name):
    setup()
    return logging.getLogger("fihi." + name)
