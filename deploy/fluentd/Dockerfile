# Log collector: Fluentd — local development only (docker compose), not deployed on Railway.
FROM fluent/fluentd:v1.19-1
USER root
COPY deploy/fluentd/fluent.conf /fluentd/etc/fluent.conf
COPY deploy/fluentd/entrypoint.sh /usr/local/bin/fluentd-entrypoint
RUN chmod 0755 /usr/local/bin/fluentd-entrypoint
# fewer Ruby heap pages and malloc arenas: ~30% less RSS for a single worker
ENV LOG_RETENTION_DAYS=30 \
    MALLOC_ARENA_MAX=2 \
    RUBY_GC_HEAP_GROWTH_FACTOR=1.1
EXPOSE 9880 24224 5140/udp
ENTRYPOINT ["tini", "--", "fluentd-entrypoint"]
