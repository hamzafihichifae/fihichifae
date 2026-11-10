# fihi-chifae — deployment guide (Railway, one service per container)

## Architecture

| Service | Image (Dockerfile) | Role | Volume | RAM (measured) |
|---|---|---|---|---|
| `frontend` | `deploy/frontend/Dockerfile` (nginx) | pages + assets, proxies `/api` → backend, `/assets/uploads/*` → storage; only **public** service | — | ~3 MB |
| `backend` | `Dockerfile` (Python, stdlib server + PyMySQL) | `/api/v1` | — | ~25 MB |
| `mysql` | `deploy/mysql/Dockerfile` (MySQL 8.4, tuned) | live tables + `products_archive`, `categories_archive` | `/var/lib/mysql` | ~130–220 MB |
| `storage` | `deploy/garage/Dockerfile` (Garage, S3) | **every image**: product photos, category pictures, admin photo, logo | `/var/lib/garage` | ~5 MB |
| `search` | `deploy/search/Dockerfile` (Meilisearch) | product search (Arabic / French / English) | `/meili_data` | ~90–120 MB |
| `fluentd` | `deploy/fluentd/Dockerfile` | log collector — **local docker compose only, not on Railway** | `fluentd-logs` (local) | ~95 MB |

On Railway: five services (no fluentd), ~265 MB measured with 100 concurrent
shoppers; the local stack with fluentd ~360 MB (see *Performance*).
Data always lives on the services' volumes; images are rebuilt on every release
and never touch it.

Images: nothing is served from the code. Every image is an object in the
`storage` bucket and the database stores its URL (`https://<shop>/media/<name>`,
built from `FIHI_PUBLIC_BASE_URL`); nginx serves `/media/*` straight from the
bucket. The images that ship with the code (logo, category pictures, demo
photos) live in `seed/media/` and are copied into the bucket at backend
start-up when missing. If the domain changes, stored URLs are rewritten at the
next start.

Search index note: Meilisearch only holds a **copy** of the catalog. The backend
rebuilds it at start-up and after every catalog change, and if `search` is down
the storefront falls back to a built-in search — losing that volume loses nothing.

## One-time setup on Railway

1. **Create the five services** from this GitHub repo (*New → GitHub repo*, five
   times), named exactly `frontend`, `backend`, `mysql`, `storage`, `search`
   (no `fluentd` on Railway: it is a local-development tool). In each service → *Settings → Config-as-code*, set the file:

   | Service | Config file |
   |---|---|
   | backend | `railway.json` |
   | frontend | `deploy/frontend/railway.json` |
   | mysql | `deploy/mysql/railway.json` |
   | storage | `deploy/garage/railway.json` |
   | search | `deploy/search/railway.json` |

2. **Volumes** (service → *Settings → Volumes*): `mysql` → `/var/lib/mysql`,
   `storage` → `/var/lib/garage`, `search` → `/meili_data`.
3. **Secrets** — generate once (`openssl rand -hex 32` / `-hex 16` / `-hex 12`):

   | Variable | Set on | Value |
   |---|---|---|
   | `MYSQL_ROOT_PASSWORD` | mysql | random |
   | `MYSQL_DATABASE` / `MYSQL_USER` / `MYSQL_PASSWORD` | mysql | `fihi` / `fihi` / random |
   | `FIHI_MYSQL_HOST` | backend | `mysql.railway.internal` |
   | `FIHI_MYSQL_DATABASE` / `FIHI_MYSQL_USER` / `FIHI_MYSQL_PASSWORD` | backend | same as on mysql |
   | `GARAGE_RPC_SECRET` | storage | `openssl rand -hex 32` |
   | `GARAGE_ACCESS_KEY` | storage | `GK` + `openssl rand -hex 12` |
   | `GARAGE_SECRET_KEY` | storage | `openssl rand -hex 32` |
   | `FIHI_S3_ENDPOINT` | backend | `http://storage.railway.internal:3900` |
   | `FIHI_S3_ACCESS_KEY` / `FIHI_S3_SECRET_KEY` | backend | same as `GARAGE_ACCESS_KEY` / `GARAGE_SECRET_KEY` |
   | `MEILI_MASTER_KEY` | search | `openssl rand -hex 16` |
   | `FIHI_MEILI_URL` / `FIHI_MEILI_KEY` | backend | `http://search.railway.internal:7700` / same key |
   | `FIHI_ADMIN_PASSWORD` | backend | a long passphrase (only used if no admin exists yet) |
   | `FIHI_PUBLIC_BASE_URL` | backend | the frontend's public URL (reset links + image URLs) |
   | `FIHI_SMTP_*`, `FIHI_EMAIL_FROM` | backend | optional, to e-mail reset links |
   | `BACKEND_HOST` | frontend | `backend.railway.internal` |
   | `STORAGE_HOST` | frontend | `storage.railway.internal` |
   | `NGINX_RESOLVER` | frontend | `[fd12::10]` (Railway's private DNS) |

   Railway's references (`${{mysql.MYSQL_PASSWORD}}`) avoid copying values twice.
4. **Networking**: *Generate domain* on **`frontend` only**. Every other service
   stays on the private network.
5. To deploy **only when you decide**, turn off *Settings → Deploy → automatic
   deploys* on each service and use the workflow below (or `railway up`).

The admin's username, password, reset e-mail and WhatsApp number are changed
from the dashboard (avatar circle → الملف الشخصي). `FIHI_ADMIN_*` and
`FIHI_WHATSAPP_NUMBER` only seed a brand-new database.

## Releasing a new version (manual button)

GitHub → **Actions → "CI/CD" → Run workflow → tick *Deploy to Railway***, list
the services to deploy (default `backend,frontend`; add `mysql,storage,search`
only when their folder under `deploy/` changed). The job runs lint + tests +
security checks, then `railway up` per service. It needs:

* secret **`RAILWAY_TOKEN`** — Railway project → *Settings → Tokens* (project token);
* optional variable **`PUBLIC_URL`** (the frontend URL) for a post-deploy smoke test.

From a terminal instead: `railway login && railway link && make deploy`.

## Logs

* **Railway**: every service logs JSON lines (backend) or JSON access lines
  (nginx) to stdout — read them in Railway's log viewer. No log service runs
  there (no extra cost).
* **Local** (docker compose): every container's output goes to Fluentd through
  the Docker logging driver; one gzip file per container per day under
  `/fluentd/log/<source>/YYYY-MM-DD.log.gz`, older than `LOG_RETENTION_DAYS`
  (default 30) deleted. `make logs` or
  `docker compose exec fluentd ls /fluentd/log`.

## Railway costs (daily check)

The **"Railway usage — daily cost check"** workflow
(`.github/workflows/railway-usage.yml`) runs every day at 07:00 UTC, separate
from CI/CD (it never builds or deploys). Its run page shows the usage of the
current billing period, the projected bill and a per-service / per-resource
breakdown, compared with the budget: the Hobby plan's included $5, or the
hard usage limit set in Railway (*Workspace → Usage → Usage limits*). When the
projection reaches `RAILWAY_WARN_PCT` % (default 80) of the budget, the run
fails, so GitHub e-mails you. Setup:

* secret **`RAILWAY_API_TOKEN`**: Railway → *Account Settings → Tokens* →
  create an account token (a project token cannot read billing);
* optional variables `RAILWAY_WORKSPACE_ID`, `RAILWAY_WARN_PCT`, `RAILWAY_BUDGET_USD`.

Tip: also set a hard usage limit in Railway itself, so services stop instead
of running up a bill if something goes wrong.

## Performance (load) test

Runs automatically after every push to `main`, or on demand (**Actions → CI/CD →
Run workflow**, tick *Run the performance test*). Each stage starts a fresh copy of
the whole stack (backend limited to 1 vCPU / 512 MB by default, demo catalog); Locust
simulates shoppers browsing, searching, loading the catalog and ordering, plus one
admin on the dashboard. The **perf-report** artifact holds `report.html` and a
per-container memory snapshot per stage (`u<N>_stack_stats.txt`). Locally: `make perf`.

Measured locally (100 users, 30 s): 2,102 requests, 0 failures, p95 74 ms
(search p95 93 ms); backend 26 MB, whole stack ~360 MB.

## Backups (free)

Dashboard → **نسخة احتياطية** downloads a zip with a consistent SQL dump of the
database (`fihi-chifae.sql`, restorable with `mysql fihi < fihi-chifae.sql`) and
every uploaded image (`GET /api/v1/admin/backup`). Do it before big changes and
keep a copy off-platform.

## Local development

```bash
cp .env.example .env              # set the passwords / keys (FIHI_ENV=development locally)
docker compose up -d --build      # the whole stack -> http://localhost:8080
make test                         # tests use the compose MySQL/Garage/Meilisearch and
                                  # delete everything they create (tests/conftest.py)
python server.py --port 8000      # backend alone (needs MySQL; local disk for images,
                                  # built-in search when FIHI_S3_* / FIHI_MEILI_* are empty)
```

## Security summary

* Only `frontend` is public; backend, database, storage, search and logs are on
  the private network.
* Admin pages and admin API require an HttpOnly + Secure + SameSite=Strict session
  cookie; nginx checks it (`auth_request`) before serving `/admin*.html`.
* Changing the admin's username, password, e-mail or phone requires the current
  password; a new password or username signs every other session out.
* Prices and delivery fees are always computed on the server.
* Login, orders, newsletter, search and profile changes are rate limited per client IP.
* Strict CSP (no inline scripts), HSTS, no-sniff, frame-deny headers.
* Images are type-checked by their bytes (PNG/JPG/WEBP/GIF only, 8 MB, photo 2 MB).
* Production refuses to start without `FIHI_ADMIN_PASSWORD` on a fresh database.
