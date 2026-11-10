#!/bin/sh
# Prepares the log volume (platform volumes are mounted owned by root), starts
# the daily retention sweep, then runs Fluentd as the unprivileged user.
set -eu
mkdir -p /fluentd/log /fluentd/buffer
if [ "$(id -u)" = "0" ]; then
  chown -R fluent:fluent /fluentd/log /fluentd/buffer
  RUN="setpriv --reuid=fluent --regid=fluent --init-groups"
else
  RUN=""
fi
(
  while true; do
    find /fluentd/log -type f -mtime +"${LOG_RETENTION_DAYS:-30}" -delete 2>/dev/null || true
    find /fluentd/log -mindepth 1 -type d -empty -delete 2>/dev/null || true
    sleep 86400
  done
) &
exec $RUN fluentd -c /fluentd/etc/fluent.conf -p /fluentd/plugins
