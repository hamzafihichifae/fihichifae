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

## Deploying (automatic)

**Every push to `main` deploys**, once lint, tests and security checks pass
(GitHub → Actions → "CI/CD" → job *Deploy → Railway*). Nothing is set up by
hand in Railway: before each deploy, `scripts/railway_bootstrap.py` makes the
project match what the shop needs, adding only what is missing:

| Step | What it does |
|---|---|
| services | creates `mysql`, `storage`, `search`, `backend`, `frontend`, each building its own `Dockerfile`, with its health check and restart policy (set through Railway's API: Railway no longer accepts `railway.json` for new services); removes other services **that have no volume** (e.g. the one Railway creates when a repo is linked) |
| volumes | `mysql` → `/var/lib/mysql`, `storage` → `/var/lib/garage`, `search` → `/meili_data` |
| variables | fixed values (hosts, ports, database / bucket names, admin user, WhatsApp number) are kept in sync; services find each other through Railway references (`${{mysql.MYSQL_PASSWORD}}`, `*.railway.internal`) |
| secrets | MySQL passwords, Garage keys, Meilisearch key and the admin password are generated **once** and stored only in Railway (never in the repo or the logs) |
| domain | public domain on `frontend` only; every other service stays private |

Then `scripts/railway_deploy.sh` deploys `backend` + `frontend` (and `mysql`,
`storage`, `search` on the first deploy or when their `deploy/<folder>/`
changed), the job waits until the shop answers and shows its URL on the run page.

**Only two things are needed, once** (repo → *Settings → Secrets and variables → Actions*):

* secret **`RAILWAY_TOKEN`**: Railway project → *Settings → Tokens* (project token);
* secret **`RAILWAY_API_TOKEN`**: Railway → *Account Settings → Tokens* (account
  token; also used by the daily cost check).

**Own domain (`fihichifae.com`, Cloudflare)**: the setup step attaches
`fihichifae.com` and `www.fihichifae.com` to `frontend` and writes the DNS
records Railway asks for into Cloudflare (CNAME to the Railway domain + the
`_railway-verify` TXT, *DNS only* so Railway issues the HTTPS certificate).
Needs the repo secret **`CLOUDFLARE_API_TOKEN`** (Cloudflare → My Profile → API
Tokens → template *Edit zone DNS*, zone `fihichifae.com`); without it the run
page lists the records to add by hand. Another domain: set `FIHI_DOMAIN` in the
script's environment. `FIHI_PUBLIC_BASE_URL` follows it, and stored image URLs
are rewritten at the next backend start. The `*.up.railway.app` address keeps working.

**Admin login**: `<shop URL>/admin-login.html`, user `admin`, password in
Railway → `backend` → *Variables* → `FIHI_ADMIN_PASSWORD`. The admin's
username, password, reset e-mail and WhatsApp number are then changed from the
dashboard (avatar circle → الملف الشخصي); `FIHI_ADMIN_*` and
`FIHI_WHATSAPP_NUMBER` only seed a brand-new database.

Optional, password-reset e-mails: add `FIHI_ADMIN_EMAIL`, `FIHI_SMTP_HOST`,
`FIHI_SMTP_PORT`, `FIHI_SMTP_USER`, `FIHI_SMTP_PASSWORD`, `FIHI_EMAIL_FROM` on
`backend` in Railway (without them the reset link is written to the backend logs).

A manual run (*Actions → CI/CD → Run workflow*) deploys the current `main` too.
From a terminal: `railway login && railway link && make deploy`.

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
