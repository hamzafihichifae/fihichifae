#!/usr/bin/env bash
# Deploy services to Railway with the right config for each one.
#
#   scripts/railway_deploy.sh backend frontend        (or: mysql storage search ...)
#
# `railway up` uploads the repo and reads the railway.json at its ROOT (the
# backend's). To build each service from its own Dockerfile, the service's
# config is copied over the root railway.json for its upload, then restored.
# Needs RAILWAY_TOKEN (project token) or `railway login && railway link`.
set -euo pipefail
cd "$(dirname "$0")/.."

config_for() {
  case "$1" in
    backend) echo "railway.json" ;;
    frontend) echo "deploy/frontend/railway.json" ;;
    mysql) echo "deploy/mysql/railway.json" ;;
    storage) echo "deploy/garage/railway.json" ;;
    search) echo "deploy/search/railway.json" ;;
    *) echo "unknown service '$1' (backend|frontend|mysql|storage|search)" >&2; return 1 ;;
  esac
}

[ "$#" -gt 0 ] || set -- backend frontend
ci_flag=""
[ -n "${CI:-}" ] && ci_flag="--ci"

backup="$(mktemp)"
cp railway.json "$backup"
trap 'cp "$backup" railway.json; rm -f "$backup"' EXIT

for svc in "$@"; do
  cfg="$(config_for "$svc")"
  cp "$backup" railway.json
  [ "$cfg" = "railway.json" ] || cp "$cfg" railway.json
  echo "==> railway up --service $svc  (config: $cfg)"
  railway up --service "$svc" $ci_flag
done
