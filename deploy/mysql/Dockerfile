# MySQL service (live tables + *_archive tables).
# Railway: attach a volume at /var/lib/mysql and set MYSQL_ROOT_PASSWORD,
# MYSQL_DATABASE, MYSQL_USER, MYSQL_PASSWORD on the service.
FROM mysql:8.4
COPY deploy/mysql/my.cnf /etc/mysql/conf.d/fihi.cnf
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
  CMD mysqladmin ping -h 127.0.0.1 --silent || exit 1
EXPOSE 3306
