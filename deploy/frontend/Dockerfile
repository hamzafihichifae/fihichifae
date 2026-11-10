# Frontend: nginx serves the pages, CSS and JS, proxies /api to the backend and
# /media/* (every image) to the object storage's public website endpoint.
FROM nginx:1.28-alpine
RUN rm -f /etc/nginx/conf.d/default.conf
COPY deploy/frontend/nginx.conf /etc/nginx/nginx.conf
COPY deploy/frontend/default.conf.template /etc/nginx/templates/default.conf.template
COPY deploy/frontend/40-fihi-logging.sh /docker-entrypoint.d/40-fihi-logging.sh
RUN chmod 0755 /docker-entrypoint.d/40-fihi-logging.sh
COPY index.html info.html admin.html admin-add.html admin-login.html admin-reset.html /usr/share/nginx/html/
COPY assets /usr/share/nginx/html/assets
# Railway injects PORT; the backend / storage are reached on the private network.
ENV PORT=8080 \
    BACKEND_HOST=backend \
    BACKEND_PORT=8000 \
    STORAGE_HOST=storage \
    STORAGE_WEB_PORT=3902 \
    STORAGE_BUCKET=uploads \
    NGINX_RESOLVER=127.0.0.11 \
    FLUENTD_SYSLOG= \
    NGINX_ENVSUBST_FILTER=^(PORT|BACKEND_|STORAGE_|NGINX_RESOLVER)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -q -O /dev/null "http://127.0.0.1:${PORT}/healthz" || exit 1
EXPOSE 8080
