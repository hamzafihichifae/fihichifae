#!/usr/bin/env bash
# Deploy services to Railway, in the given order.
#
#   scripts/railway_deploy.sh backend frontend        (or: mysql storage search ...)
#
# Each service builds its own Dockerfile: scripts/railway_bootstrap.py sets
# the Dockerfile path, health check and restart policy on every service
# through the Railway API (Railway no longer accepts railway.json for new
# services). Needs RAILWAY_TOKEN (project token) or RAILWAY_API_TOKEN plus
# `railway link`, or `railway login && railway link` locally.
set -euo pipefail
cd "$(dirname "$0")/.."

[ "$#" -gt 0 ] || set -- backend frontend
ci_flag=""
[ -n "${CI:-}" ] && ci_flag="--ci"

for svc in "$@"; do
  case "$svc" in
    backend | frontend | mysql | storage | search) ;;
    *) echo "unknown service '$svc' (backend|frontend|mysql|storage|search)" >&2; exit 1 ;;
  esac
  echo "==> railway up --service $svc"
  log="$(mktemp)"
  if ! railway up --service "$svc" $ci_flag 2>&1 | tee "$log"; then
    # GitHub Actions: show the end of the output as an annotation on the run page
    if [ -n "${GITHUB_ACTIONS:-}" ]; then
      echo "::error title=railway up $svc failed::$(tail -n 20 "$log" | sed ':a;N;$!ba;s/\n/%0A/g')"
    fi
    rm -f "$log"
    exit 1
  fi
  rm -f "$log"
done
