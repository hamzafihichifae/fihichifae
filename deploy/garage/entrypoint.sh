#!/bin/sh
# Writes garage.toml from the environment, starts Garage, then makes sure
# (idempotently) that the single-node layout, the backend's access key and
# the public-read "uploads" bucket exist.
set -eu

: "${GARAGE_RPC_SECRET:?set GARAGE_RPC_SECRET (64 hex chars: openssl rand -hex 32)}"
: "${GARAGE_ACCESS_KEY:?set GARAGE_ACCESS_KEY (GK + 24 hex chars)}"
: "${GARAGE_SECRET_KEY:?set GARAGE_SECRET_KEY (64 hex chars)}"
DATA="${GARAGE_DATA_DIR:-/var/lib/garage}"
mkdir -p "$DATA/meta" "$DATA/data"

cat > /etc/garage.toml <<CONF
metadata_dir = "$DATA/meta"
data_dir = "$DATA/data"
db_engine = "sqlite"
replication_factor = 1
compression_level = "none"
rpc_bind_addr = "[::]:3901"
rpc_public_addr = "127.0.0.1:3901"
rpc_secret = "$GARAGE_RPC_SECRET"

[s3_api]
s3_region = "garage"
api_bind_addr = "[::]:3900"
root_domain = ".s3.garage"

[s3_web]
bind_addr = "[::]:3902"
root_domain = ".web.garage"
index = "index.html"
CONF

garage -c /etc/garage.toml server &
PID=$!
trap 'kill -TERM $PID 2>/dev/null; wait $PID' TERM INT

g() { garage -c /etc/garage.toml "$@"; }
i=0
until g status >/dev/null 2>&1; do
  i=$((i + 1)); [ $i -gt 60 ] && { echo "[garage] did not start"; exit 1; }
  sleep 1
done

if ! g layout show 2>/dev/null | grep -q "dc1"; then
  NODE=$(g node id -q | cut -d@ -f1)
  g layout assign -z dc1 -c "$GARAGE_CAPACITY" "$NODE"
  g layout apply --version 1
  echo "[garage] single-node layout applied"
fi
g key info "$GARAGE_ACCESS_KEY" >/dev/null 2>&1 \
  || g key import --yes -n fihi-backend "$GARAGE_ACCESS_KEY" "$GARAGE_SECRET_KEY"
g bucket info "$GARAGE_BUCKET" >/dev/null 2>&1 || g bucket create "$GARAGE_BUCKET"
g bucket allow --read --write --owner "$GARAGE_BUCKET" --key "$GARAGE_ACCESS_KEY" >/dev/null
g bucket website --allow "$GARAGE_BUCKET" >/dev/null
echo "[garage] ready: bucket '$GARAGE_BUCKET' (S3 :3900, public web :3902)"

wait $PID
