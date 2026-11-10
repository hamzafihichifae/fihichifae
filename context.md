# Project context (compact)
Root: C:\Users\eurek\Downloads\fihi-chifae\mielyoussef-clone
Stack (one container each; Railway: 5 services, no fluentd; docker-compose.yml locally: 6):
frontend nginx (pages, /api proxy, /assets/uploads -> Garage web endpoint, auth_request for admin pages) |
backend Python stdlib server + PyMySQL | mysql 8.4 (live tables + products_archive / categories_archive) |
storage Garage S3 (bucket "uploads" = EVERY image; DB stores URLs MEDIA_BASE_URL/<name>, nginx /media/*;
seed/media/* copied to the bucket at start; old assets/... paths rewritten by db.sync_media_urls) | search Meilisearch (app/search.py, built-in fallback) |
fluentd = LOCAL DEV ONLY (docker driver :24224; daily gzip files, 30 days); not a Railway service.
Daily Railway cost check: .github/workflows/railway-usage.yml + scripts/railway_usage.py.
API v1 under /api/v1 with JSON error envelope; legacy /api/* -> 410; method -> 405; crash -> 500.
Auth: PBKDF2-HMAC-SHA256 210k, sessions hashed in MySQL (TTL 8h), login throttled 5/15m -> 429.
Admin profile (avatar circle, top-right of every admin page): username, password, reset e-mail,
shop WhatsApp phone, optional photo; current password required; a new password or username
signs the other sessions out. Values live in the meta table.
Orders: customer filter (buyer name), current month by default; "all periods" -> whole history + summary.
Sizes: units g / kg / L; id "250g", shown "250 g" (value then unit, dir=ltr) in every language.
Tests: real MySQL / Garage / Meilisearch from .env; every test deletes what it creates (tests/conftest.py).
