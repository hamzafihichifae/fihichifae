# Object storage for uploaded images: Garage (Rust, ~20-40 MB RAM, S3 API).
# The official image is FROM scratch; Alpine adds a shell for the one-time
# bootstrap (node layout, access key, public "uploads" bucket).
# Railway: attach a volume at /var/lib/garage and set GARAGE_RPC_SECRET,
# GARAGE_ACCESS_KEY, GARAGE_SECRET_KEY (see .env.example).
FROM dxflrs/garage:v2.1.0 AS garage

FROM alpine:3.22
RUN apk add --no-cache tini
COPY --from=garage /garage /usr/local/bin/garage
COPY deploy/garage/entrypoint.sh /usr/local/bin/garage-entrypoint
RUN chmod 0755 /usr/local/bin/garage-entrypoint
ENV GARAGE_BUCKET=uploads \
    GARAGE_CAPACITY=5G \
    RUST_LOG=garage=warn,netapp=warn
EXPOSE 3900 3902
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD garage -c /etc/garage.toml status >/dev/null 2>&1 || exit 1
ENTRYPOINT ["/sbin/tini", "--", "garage-entrypoint"]
