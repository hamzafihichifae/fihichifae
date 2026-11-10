# Product search: Meilisearch (Rust, ~50-80 MB RAM for this catalog).
# Railway: attach a volume at /meili_data and set MEILI_MASTER_KEY (>= 16 bytes).
FROM getmeili/meilisearch:v1.24
ENV MEILI_ENV=production \
    MEILI_NO_ANALYTICS=true \
    MEILI_DB_PATH=/meili_data/data.ms \
    MEILI_DUMP_DIR=/meili_data/dumps \
    MEILI_SNAPSHOT_DIR=/meili_data/snapshots \
    MEILI_HTTP_ADDR=[::]:7700 \
    MEILI_MAX_INDEXING_MEMORY=128Mb \
    MEILI_MAX_INDEXING_THREADS=1 \
    MEILI_LOG_LEVEL=WARN
EXPOSE 7700
