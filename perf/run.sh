#!/usr/bin/env bash
# Load test the whole stack (frontend -> backend -> MySQL / Garage / Meilisearch)
# at several crowd sizes and record resource usage, then build the report.
#
#   PERF_USERS="5 100 1000" PERF_DURATION=60 PERF_CPUS=1 PERF_MEMORY=512m bash perf/run.sh
#
# Each stage starts a FRESH copy of the stack (compose project "fihi-perf",
# its own volumes, demo catalog) with the same backend CPU/RAM limits
# (default: 1 vCPU / 512 MB), so stages are comparable. Nothing touches real data.
set -uo pipefail

USERS="${PERF_USERS:-5 100 1000}"
DURATION="${PERF_DURATION:-60}"
OUT="${PERF_OUT:-perf-results}"
export PERF_CPUS="${PERF_CPUS:-1}" PERF_MEMORY="${PERF_MEMORY:-512m}" PERF_PORT="${PERF_PORT:-18080}"
ADMIN_PASSWORD=perf-admin-pass
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
ENV_FILE="$(mktemp)"
COMPOSE=(docker compose -p fihi-perf --env-file "$ENV_FILE" -f "$ROOT/docker-compose.yml" -f "$HERE/docker-compose.perf.yml")

# throw-away secrets for this run only
rnd() { python -c "import secrets,sys; print(secrets.token_hex(int(sys.argv[1])))" "$1"; }
S3_KEY="GK$(rnd 12)"; S3_SECRET="$(rnd 32)"
cat > "$ENV_FILE" <<ENV
FIHI_ENV=production
FIHI_ADMIN_USER=admin
FIHI_ADMIN_PASSWORD=$ADMIN_PASSWORD
FIHI_MYSQL_PASSWORD=$(rnd 16)
MYSQL_ROOT_PASSWORD=$(rnd 16)
FIHI_S3_ACCESS_KEY=$S3_KEY
FIHI_S3_SECRET_KEY=$S3_SECRET
GARAGE_RPC_SECRET=$(rnd 32)
FIHI_MEILI_KEY=$(rnd 16)
FIHI_TRUST_PROXY=1
ENV
export FIHI_ENV_FILE="$ENV_FILE"   # the backend's env_file in docker-compose.yml

USERS="${USERS//,/ }"
mkdir -p "$OUT"
echo "{\"image\": \"stack (compose)\", \"users\": \"$USERS\", \"duration_s\": $DURATION, \"cpus\": \"$PERF_CPUS\", \"memory\": \"$PERF_MEMORY\", \"git_sha\": \"${GITHUB_SHA:-local}\", \"started\": \"$(date -u +%FT%TZ)\"}" > "$OUT/run.json"

stop_all() {
  [ -n "${SAMPLER:-}" ] && kill "$SAMPLER" 2>/dev/null
  "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1
}
trap 'stop_all; rm -f "$ENV_FILE"' EXIT

"${COMPOSE[@]}" build -q
for N in $USERS; do
  echo "================ stage: $N concurrent users (${DURATION}s, ${PERF_CPUS} vCPU, ${PERF_MEMORY}) ================"
  stop_all
  "${COMPOSE[@]}" up -d --wait >/dev/null 2>&1 || "${COMPOSE[@]}" up -d >/dev/null
  BASE="http://127.0.0.1:$PERF_PORT"
  for _ in $(seq 1 120); do curl -fs "$BASE/api/v1/ping" >/dev/null && break; sleep 0.5; done
  BACKEND="$("${COMPOSE[@]}" ps -q backend)"

  # resource sampler (backend container): one JSON line per second, timestamped
  docker stats --format '{{json .}}' "$BACKEND" 2>/dev/null \
    | while IFS= read -r line; do
        line="${line//$'\e'\[2J/}"; line="${line//$'\e'\[H/}"; line="${line//$'\e'\[J/}"
        [ -n "$line" ] && printf '%s|%s\n' "$(date +%s.%N)" "$line"
      done > "$OUT/u${N}_docker_stats.txt" &
  SAMPLER=$!

  RATE=$(( N / 10 )); [ "$RATE" -lt 1 ] && RATE=1   # ramp up over ~10 s
  PERF_ADMIN_PASSWORD="$ADMIN_PASSWORD" locust -f "$HERE/locustfile.py" --headless \
    -u "$N" -r "$RATE" -t "${DURATION}s" --host "$BASE" \
    --csv "$OUT/u${N}" --csv-full-history --html "$OUT/u${N}_locust.html" \
    --only-summary --stop-timeout 5 --loglevel WARNING || true

  kill "$SAMPLER" 2>/dev/null; SAMPLER=
  docker stats --no-stream --format '{{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}' \
    $("${COMPOSE[@]}" ps -q) > "$OUT/u${N}_stack_stats.txt" 2>/dev/null
  docker inspect -f '{"oom_killed": {{.State.OOMKilled}}, "restarts": {{.RestartCount}}, "running": {{.State.Running}}}' "$BACKEND" \
    > "$OUT/u${N}_container.json" 2>/dev/null || echo '{"running": false}' > "$OUT/u${N}_container.json"
  docker logs --tail 300 "$BACKEND" > "$OUT/u${N}_server.log" 2>&1
done

python "$HERE/report.py" "$OUT"
