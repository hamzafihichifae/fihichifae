#!/bin/sh
# Access/error logs: stdout always; also syslog (UDP) to Fluentd when
# FLUENTD_SYSLOG is set (e.g. fluentd:5140 with docker compose; unset on Railway).
set -eu
OUT=/etc/nginx/conf.d/logging.inc
echo 'access_log /dev/stdout fihi_json;' > "$OUT"
if [ -n "${FLUENTD_SYSLOG:-}" ]; then
  echo "access_log syslog:server=${FLUENTD_SYSLOG},tag=nginx fihi_json;" >> "$OUT"
  echo "error_log syslog:server=${FLUENTD_SYSLOG},tag=nginx_error warn;" >> "$OUT"
fi
