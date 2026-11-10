"""Prepare the Railway project so a deploy leaves a working shop. Idempotent.

Run by the CI/CD deploy job before every deploy. It only adds what is missing:

* the five services (mysql, storage, search, backend, frontend), each building
  its own Dockerfile, with its health check / restart policy set through the
  API (Railway no longer accepts railway.json for new services);
* their volumes (mysql, storage, search);
* every variable: fixed values are kept in sync, secrets (passwords, keys) are
  generated ONCE and stored only in Railway, never in the repo or the logs;
* the public domain, on the frontend only;
* removes stray services (e.g. one Railway created when the repo was linked)
  as long as they have no volume, so no data can be lost.

Then it prints which services to deploy (infra only on the first deploy or
when its deploy/<folder> changed; backend + frontend always) and the shop URL.

Environment:
    RAILWAY_TOKEN      project token (finds the project + environment)
    RAILWAY_API_TOKEN  account token (creates services, volumes, variables...)
    CHANGED_FILES      files changed by the push, one per line, or "ALL"
    GITHUB_OUTPUT      set by GitHub Actions: receives deploy=... and url=...
"""

import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request

API = "https://backboard.railway.com/graphql/v2"

# name -> (extra settings, Dockerfile, volume mount or None, folder that triggers a redeploy)
SERVICES = {
    "mysql": (
        {},
        "deploy/mysql/Dockerfile",
        "/var/lib/mysql",
        "deploy/mysql/",
    ),
    "storage": (
        {},
        "deploy/garage/Dockerfile",
        "/var/lib/garage",
        "deploy/garage/",
    ),
    "search": (
        {},
        "deploy/search/Dockerfile",
        "/meili_data",
        "deploy/search/",
    ),
    "backend": (
        {"healthcheckPath": "/api/v1/ping", "healthcheckTimeout": 120},
        "Dockerfile",
        None,
        None,
    ),
    "frontend": (
        {"healthcheckPath": "/healthz", "healthcheckTimeout": 60},
        "deploy/frontend/Dockerfile",
        None,
        None,
    ),
}
ORDER = ["mysql", "storage", "search", "backend", "frontend"]
INFRA = {"mysql", "storage", "search"}
FRONTEND_PORT = 8080
# The shop's own domain (its Cloudflare zone); the first one is the main address.
ZONE = os.environ.get("FIHI_DOMAIN", "fihichifae.com")
# Railway Hobby allows one custom domain per service: only the main one.
# Extra ones (comma separated FIHI_EXTRA_DOMAINS, e.g. www.fihichifae.com) are
# attempted, and only warn when the plan refuses them.
CUSTOM_DOMAINS = ([ZONE] if ZONE else []) + [
    d.strip() for d in os.environ.get("FIHI_EXTRA_DOMAINS", "").split(",") if d.strip()
]


def _secret(nbytes):
    return lambda: secrets.token_hex(nbytes)


def _passphrase():
    return "-".join(secrets.token_urlsafe(6) for _ in range(4))


# Fixed values: always kept as written here. Railway resolves ${{service.VAR}}.
FIXED = {
    "mysql": {"MYSQL_DATABASE": "fihi", "MYSQL_USER": "fihi"},
    "storage": {"GARAGE_BUCKET": "uploads"},
    "search": {},
    "backend": {
        "FIHI_ENV": "production",
        "PORT": "8000",
        "FIHI_ADMIN_USER": "admin",
        "FIHI_WHATSAPP_NUMBER": "212681771457",
        # first reset address only (replaces the old placeholder); the admin
        # changes it from the profile panel afterwards
        "FIHI_ADMIN_EMAIL": "hamza.fihichifae@gmail.com",
        "FIHI_PUBLIC_BASE_URL": (
            "https://" + ZONE if ZONE else "https://${{frontend.RAILWAY_PUBLIC_DOMAIN}}"
        ),
        "FIHI_MYSQL_HOST": "${{mysql.RAILWAY_PRIVATE_DOMAIN}}",
        "FIHI_MYSQL_PORT": "3306",
        "FIHI_MYSQL_DATABASE": "${{mysql.MYSQL_DATABASE}}",
        "FIHI_MYSQL_USER": "${{mysql.MYSQL_USER}}",
        "FIHI_MYSQL_PASSWORD": "${{mysql.MYSQL_PASSWORD}}",
        "FIHI_MYSQL_CONNECT_WAIT": "300",
        "FIHI_S3_ENDPOINT": "http://${{storage.RAILWAY_PRIVATE_DOMAIN}}:3900",
        "FIHI_S3_BUCKET": "${{storage.GARAGE_BUCKET}}",
        "FIHI_S3_ACCESS_KEY": "${{storage.GARAGE_ACCESS_KEY}}",
        "FIHI_S3_SECRET_KEY": "${{storage.GARAGE_SECRET_KEY}}",
        "FIHI_MEILI_URL": "http://${{search.RAILWAY_PRIVATE_DOMAIN}}:7700",
        "FIHI_MEILI_KEY": "${{search.MEILI_MASTER_KEY}}",
    },
    "frontend": {
        "PORT": str(FRONTEND_PORT),
        "BACKEND_HOST": "${{backend.RAILWAY_PRIVATE_DOMAIN}}",
        "BACKEND_PORT": "8000",
        "STORAGE_HOST": "${{storage.RAILWAY_PRIVATE_DOMAIN}}",
        "STORAGE_BUCKET": "${{storage.GARAGE_BUCKET}}",
        "NGINX_RESOLVER": "[fd12::10]",
    },
}
# Secrets: generated once when missing, never overwritten, never printed.
SECRETS = {
    "mysql": {"MYSQL_ROOT_PASSWORD": _secret(16), "MYSQL_PASSWORD": _secret(16)},
    "storage": {
        "GARAGE_RPC_SECRET": _secret(32),
        "GARAGE_ACCESS_KEY": lambda: "GK" + secrets.token_hex(12),
        "GARAGE_SECRET_KEY": _secret(32),
    },
    "search": {"MEILI_MASTER_KEY": _secret(16)},
    "backend": {"FIHI_ADMIN_PASSWORD": _passphrase},
    "frontend": {},
}
for _name, (_cfg, _dockerfile, _mount, _folder) in SERVICES.items():
    FIXED[_name]["RAILWAY_DOCKERFILE_PATH"] = _dockerfile


class RailwayError(RuntimeError):
    pass


# Credential used for every API call, chosen by find_project():
# ("account", token) -> Authorization: Bearer, ("project", token) -> Project-Access-Token
AUTH = {"kind": "account", "token": ""}


def gql(query, variables=None, project_token=None, account_token=None):
    headers = {"Content-Type": "application/json", "User-Agent": "fihi-chifae-bootstrap"}
    if project_token:
        headers["Project-Access-Token"] = project_token
    elif account_token:
        headers["Authorization"] = "Bearer " + account_token
    elif AUTH["kind"] == "project":
        headers["Project-Access-Token"] = AUTH["token"]
    else:
        headers["Authorization"] = "Bearer " + AUTH["token"]
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    for attempt in range(4):
        req = urllib.request.Request(API, data=body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - fixed https URL
                data = json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code >= 500 and attempt < 3:
                time.sleep(3 * (attempt + 1))
                continue
            raise RailwayError(f"HTTP {exc.code}: {exc.read()[:300]!r}") from exc
        if data.get("errors"):
            raise RailwayError("; ".join(e.get("message", "?") for e in data["errors"]))
        return data["data"]
    raise RailwayError("Railway API unavailable")


def log(msg):
    print(msg, flush=True)


def _as_project_token(token):
    try:
        d = gql("{ projectToken { projectId environmentId } }", project_token=token)
    except RailwayError:
        return None
    return d["projectToken"]["projectId"], d["projectToken"]["environmentId"]


def _projects_of(token):
    """Projects an account / workspace token can see: [(id, name, {env name: id})]."""
    node = "id name environments { edges { node { id name } } }"
    found = {}
    queries = [
        "{ me { workspaces { projects(first: 100) { edges { node { " + node + " } } } } } }",
        "{ projects(first: 100) { edges { node { " + node + " } } } }",
    ]
    for q in queries:
        try:
            d = gql(q, account_token=token)
        except RailwayError:
            continue
        conns = [w["projects"] for w in d["me"]["workspaces"]] if "me" in d else [d["projects"]]
        for conn in conns:
            for e in conn["edges"]:
                n = e["node"]
                envs = {x["node"]["name"]: x["node"]["id"] for x in n["environments"]["edges"]}
                found[n["id"]] = (n["id"], n["name"], envs)
    return list(found.values())


def find_project():
    """Find the project and environment from whichever secrets were given.

    Works whether RAILWAY_TOKEN / RAILWAY_API_TOKEN hold a project token, an
    account token or a workspace token, or were swapped. Returns
    (project_id, env_id, cli) where cli = (env var, token) for the Railway CLI.
    """
    secrets_given = [
        (name, os.environ[name])
        for name in ("RAILWAY_TOKEN", "RAILWAY_API_TOKEN")
        if os.environ.get(name)
    ]
    project_hit = None  # (secret name, token, (project id, env id))
    accounts = []  # (secret name, token, projects it can see)
    for name, tok in secrets_given:
        hit = _as_project_token(tok)
        if hit:
            project_hit = project_hit or (name, tok, hit)
            continue
        projects = _projects_of(tok)
        if projects:
            accounts.append((name, tok, projects))
        else:
            log(f"! secret {name} is not a valid Railway token (ignored)")

    if project_hit:
        name, tok, (pid, eid) = project_hit
        if accounts:  # an account token can do everything; prefer it for the API
            AUTH.update(kind="account", token=accounts[0][1])
        else:
            AUTH.update(kind="project", token=tok)
        log(f"project found from the project token in {name}")
        return pid, eid, ("project", name)

    if not accounts:
        raise RailwayError(
            "neither secret is a valid Railway token: create a project token "
            "(Railway project -> Settings -> Tokens) and put it in RAILWAY_TOKEN"
        )
    name, account, projects = accounts[0]
    if len(projects) > 1:
        ours = [p for p in projects if "fihi" in p[1].lower()]
        projects = ours if len(ours) == 1 else projects
    if len(projects) > 1:
        names = ", ".join(p[1] for p in projects)
        raise RailwayError(f"several Railway projects ({names}): keep one, or add a project token")
    pid, pname, envs = projects[0]
    eid = envs.get("production") or next(iter(envs.values()))
    AUTH.update(kind="account", token=account)
    log(f"project '{pname}' found from the account token in {name}")
    return pid, eid, ("account", name)


def load_state(project_id, env_id):
    data = gql(
        """query($p:String!,$e:String!){
          project(id:$p){ services { edges { node { id name } } } }
          environment(id:$e, projectId:$p){
            serviceInstances { edges { node { serviceId latestDeployment { status } } } }
            volumeInstances { edges { node { serviceId mountPath } } }
          }
        }""",
        {"p": project_id, "e": env_id},
    )
    services = {e["node"]["name"]: e["node"]["id"] for e in data["project"]["services"]["edges"]}
    env = data["environment"]
    status = {}
    for e in env["serviceInstances"]["edges"]:
        dep = e["node"]["latestDeployment"]
        status[e["node"]["serviceId"]] = dep["status"] if dep else None
    volumes = {}
    for e in env["volumeInstances"]["edges"]:
        volumes.setdefault(e["node"]["serviceId"], []).append(e["node"]["mountPath"])
    return services, status, volumes


def ensure_services(project_id, env_id, services, volumes):
    for name, sid in list(services.items()):
        if name in SERVICES:
            continue
        if volumes.get(sid):
            log(f"! keeping stray service '{name}': it has a volume (delete it by hand if unused)")
            continue
        gql(
            "mutation($id:String!,$e:String!){ serviceDelete(id:$id, environmentId:$e) }",
            {"id": sid, "e": env_id},
        )
        log(f"- removed stray service '{name}' (no volume)")
        del services[name]
    for name in ORDER:
        if name not in services:
            data = gql(
                "mutation($i:ServiceCreateInput!){ serviceCreate(input:$i){ id } }",
                {"i": {"projectId": project_id, "environmentId": env_id, "name": name}},
            )
            services[name] = data["serviceCreate"]["id"]
            log(f"+ created service '{name}'")
        extra, dockerfile, _mount, _folder = SERVICES[name]
        settings = {
            "dockerfilePath": dockerfile,
            "numReplicas": 1,
            "restartPolicyType": "ON_FAILURE",
            "restartPolicyMaxRetries": 10,
            **extra,
        }
        gql(
            """mutation($s:String!,$e:String!,$i:ServiceInstanceUpdateInput!){
              serviceInstanceUpdate(serviceId:$s, environmentId:$e, input:$i) }""",
            {
                "s": services[name],
                "e": env_id,
                "i": settings,
            },
        )


def ensure_volumes(project_id, env_id, services, volumes):
    for name in ORDER:
        mount = SERVICES[name][2]
        sid = services[name]
        if mount and mount not in volumes.get(sid, []):
            gql(
                "mutation($i:VolumeCreateInput!){ volumeCreate(input:$i){ id } }",
                {
                    "i": {
                        "projectId": project_id,
                        "environmentId": env_id,
                        "serviceId": sid,
                        "mountPath": mount,
                    }
                },
            )
            volumes.setdefault(sid, []).append(mount)
            log(f"+ volume {mount} on '{name}'")


def ensure_variables(project_id, env_id, services):
    for name in ORDER:
        sid = services[name]
        current = gql(
            """query($p:String!,$e:String!,$s:String!){
              variables(projectId:$p, environmentId:$e, serviceId:$s, unrendered:true) }""",
            {"p": project_id, "e": env_id, "s": sid},
        )["variables"]
        changes = {k: v for k, v in FIXED[name].items() if current.get(k) != v}
        new_secrets = [k for k in SECRETS[name] if not current.get(k)]
        for key in new_secrets:
            changes[key] = SECRETS[name][key]()
        if not changes:
            continue
        gql(
            "mutation($i:VariableCollectionUpsertInput!){ variableCollectionUpsert(input:$i) }",
            {
                "i": {
                    "projectId": project_id,
                    "environmentId": env_id,
                    "serviceId": sid,
                    "variables": changes,
                    "replace": False,
                    "skipDeploys": True,
                }
            },
        )
        shown = sorted(set(changes) - set(new_secrets))
        log(
            f"~ '{name}': {len(shown)} setting(s) updated"
            + (f", {len(new_secrets)} secret(s) generated" if new_secrets else "")
        )


def ensure_domain(project_id, env_id, services):
    """The Railway-provided domain (*.up.railway.app) on the frontend."""
    sid = services["frontend"]
    q = """query($p:String!,$e:String!,$s:String!){
      domains(projectId:$p, environmentId:$e, serviceId:$s){ serviceDomains { domain } } }"""
    found = gql(q, {"p": project_id, "e": env_id, "s": sid})["domains"]["serviceDomains"]
    names = [x["domain"] for x in found]
    if not names:
        data = gql(
            "mutation($i:ServiceDomainCreateInput!){ serviceDomainCreate(input:$i){ domain } }",
            {"i": {"environmentId": env_id, "serviceId": sid, "targetPort": FRONTEND_PORT}},
        )
        names = [data["serviceDomainCreate"]["domain"]]
        log(f"+ public domain {names[0]}")
    return "https://" + names[0]


# ---------------------------------------------------------------- custom domain
CF_API = "https://api.cloudflare.com/client/v4"
_CUSTOM_STATUS = """status { verified verificationDnsHost verificationToken certificateStatus
  dnsRecords { fqdn hostlabel zone recordType requiredValue currentValue status } }"""


def cloudflare(method, path, payload=None):
    req = urllib.request.Request(  # noqa: S310 - fixed https URL
        CF_API + path,
        method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": "Bearer " + os.environ["CLOUDFLARE_API_TOKEN"],
            "Content-Type": "application/json",
            "User-Agent": "fihi-chifae-bootstrap",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - fixed https URL
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        data = json.loads(exc.read() or b"{}")
    if not data.get("success"):
        raise RailwayError(f"Cloudflare {method} {path}: {data.get('errors')}")
    return data["result"]


def wanted_records(domain_status, zone):
    """[(type, fqdn, value)] that Railway needs for one custom domain."""
    out = []
    for r in domain_status.get("dnsRecords") or []:
        rtype = (r.get("recordType") or "").replace("DNS_RECORD_TYPE_", "")
        if rtype in ("CNAME", "A", "TXT") and r.get("requiredValue"):
            fqdn = r.get("fqdn") or ".".join(x for x in (r.get("hostlabel"), zone) if x)
            out.append((rtype, fqdn.rstrip("."), r["requiredValue"]))
    host = domain_status.get("verificationDnsHost")
    token = domain_status.get("verificationToken")
    if host and token and not domain_status.get("verified"):
        fqdn = host.rstrip(".")
        if not fqdn.endswith(zone):
            fqdn = f"{fqdn}.{zone}"
        out.append(("TXT", fqdn, token))
    return out


def upsert_cloudflare_records(zone, records):
    """Create / correct the records; leaves unrelated records alone."""
    zones = cloudflare("GET", f"/zones?name={zone}")
    if not zones:
        raise RailwayError(f"the Cloudflare token cannot see the zone {zone}")
    zid = zones[0]["id"]
    for rtype, fqdn, value, *extra in records:
        existing = cloudflare("GET", f"/zones/{zid}/dns_records?name={fqdn}&per_page=100")
        if rtype == "CNAME":
            # a name holding a CNAME can hold nothing else that routes traffic
            in_the_way = [r for r in existing if r["type"] in ("A", "AAAA", "CNAME")]
        else:
            in_the_way = [
                r for r in existing if r["type"] == rtype and r["content"].strip('"') == value
            ]
        if any(r["type"] == rtype and r["content"].strip('"') == value for r in in_the_way):
            continue  # already right
        body = {"type": rtype, "name": fqdn, "content": value, "ttl": 1}
        if rtype in ("CNAME", "A"):
            body["proxied"] = False  # DNS only: Railway issues the HTTPS certificate
        if rtype == "MX":
            body["priority"] = int(extra[0]) if extra else 10
        for r in in_the_way:
            cloudflare("DELETE", f"/zones/{zid}/dns_records/{r['id']}")
        cloudflare("POST", f"/zones/{zid}/dns_records", body)
        log(f"~ Cloudflare {rtype} {fqdn} -> {value[:48]}")


# ---------------------------------------------------------------- e-mail (Resend)
RESEND_API = "https://api.resend.com"
SENDER = "Fihi Chifae <no-reply@{zone}>"


def resend(method, path, payload=None):
    req = urllib.request.Request(  # noqa: S310 - fixed https URL
        RESEND_API + path,
        method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": "Bearer " + os.environ["RESEND_API_KEY"],
            "Content-Type": "application/json",
            "User-Agent": "fihi-chifae-bootstrap",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - fixed https URL
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:300].decode("utf-8", "replace")
        raise RailwayError(f"Resend {method} {path}: HTTP {exc.code} {detail}") from exc


def resend_records(domain):
    """[(type, fqdn, value, priority)] Resend needs (SPF / DKIM / bounce MX)."""
    out = []
    for r in domain.get("records") or []:
        name = (r.get("name") or "").rstrip(".")
        fqdn = name if name == ZONE or name.endswith("." + ZONE) else f"{name}.{ZONE}"
        if not name:
            fqdn = ZONE
        rtype = (r.get("type") or "").upper()
        if rtype in ("MX", "TXT", "CNAME") and r.get("value"):
            out.append((rtype, fqdn, r["value"], r.get("priority") or 10))
    return out


def ensure_email():
    """Prepare the shop's e-mail sending. Returns the backend variables to set.

    With RESEND_API_KEY: registers the shop domain at Resend, writes its DNS
    records into Cloudflare and asks Resend to verify it. Until the domain is
    verified, the backend sends from Resend's shared address (it only delivers
    to the Resend account's own e-mail); once verified, from no-reply@<domain>.
    """
    key = os.environ.get("RESEND_API_KEY", "").strip()
    if not key:
        log("! no RESEND_API_KEY secret: reset links are only written to the backend logs")
        return {}
    env = {"FIHI_RESEND_API_KEY": key}
    if not ZONE:
        return env
    try:
        listed = resend("GET", "/domains").get("data") or []
        found = next((d for d in listed if d.get("name") == ZONE), None)
        if found is None:
            found = resend("POST", "/domains", {"name": ZONE})
            log(f"+ Resend domain {ZONE}")
        domain = resend("GET", f"/domains/{found['id']}")
    except RailwayError as exc:
        # e.g. a "sending access" key cannot manage domains: still send, from
        # Resend's shared address
        print(f"::warning title=Resend domain not managed::{exc}", flush=True)
        return env
    # the backend sends from the shop domain and falls back to Resend's shared
    # sender by itself while the domain is not verified yet
    env["FIHI_EMAIL_FROM"] = SENDER.format(zone=ZONE)
    if domain.get("status") == "verified":
        return env
    records = resend_records(domain)
    if os.environ.get("CLOUDFLARE_API_TOKEN"):
        upsert_cloudflare_records(ZONE, records)
    elif records:
        lines = "%0A".join(f"{t} {n} -> {v}" for t, n, v, _p in records)
        print(f"::warning title=Add these e-mail DNS records in Cloudflare::{lines}")
    try:
        resend("POST", f"/domains/{found['id']}/verify")
        log(f"~ Resend verification of {ZONE} requested")
    except RailwayError as exc:
        print(f"::warning title=Resend verification::{exc}", flush=True)
    return env


def ensure_custom_domains(project_id, env_id, services):
    """Attach CUSTOM_DOMAINS to the frontend and point the Cloudflare DNS at it."""
    if not CUSTOM_DOMAINS:
        return ""
    sid = services["frontend"]
    q = (
        "query($p:String!,$e:String!,$s:String!){"
        " domains(projectId:$p, environmentId:$e, serviceId:$s){"
        " customDomains { domain " + _CUSTOM_STATUS + " } } }"
    )
    found = gql(q, {"p": project_id, "e": env_id, "s": sid})["domains"]["customDomains"]
    current = {d["domain"]: d for d in found}
    records = []
    for index, domain in enumerate(CUSTOM_DOMAINS):
        if domain not in current:
            try:
                created = gql(
                    "mutation($i:CustomDomainCreateInput!){ customDomainCreate(input:$i){ domain "
                    + _CUSTOM_STATUS
                    + " } }",
                    {
                        "i": {
                            "domain": domain,
                            "projectId": project_id,
                            "environmentId": env_id,
                            "serviceId": sid,
                            "targetPort": FRONTEND_PORT,
                        }
                    },
                )["customDomainCreate"]
            except RailwayError as exc:
                if index == 0:
                    raise
                print(f"::warning title={domain} not attached::{exc}", flush=True)
                continue
            current[domain] = created
            log(f"+ custom domain {domain} on 'frontend'")
        records += wanted_records(current[domain].get("status") or {}, ZONE)
    if os.environ.get("CLOUDFLARE_API_TOKEN"):
        upsert_cloudflare_records(ZONE, records)
    elif records:
        lines = "%0A".join(f"{t} {n} -> {v}" for t, n, v in records)
        print(f"::warning title=Add these DNS records in Cloudflare (DNS only)::{lines}")
    return "https://" + CUSTOM_DOMAINS[0]


def to_deploy(services, status, changed):
    out = []
    for name in ORDER:
        if name not in INFRA:
            out.append(name)
            continue
        folder = SERVICES[name][3]
        never_ok = status.get(services[name]) != "SUCCESS"
        touched = changed == "ALL" or any(f.startswith(folder) for f in changed)
        if never_ok or touched:
            out.append(name)
    return out


DEPLOY_TOKEN_PREFIX = "ci-deploy"  # noqa: S105 - a name prefix, not a secret


def delete_deploy_tokens(project_id):
    """Remove the short-lived CLI tokens this script created on earlier runs."""
    data = gql(
        "query($p:String!){ projectTokens(projectId:$p, first:100){ edges { node { id name } } } }",
        {"p": project_id},
    )
    for e in data["projectTokens"]["edges"]:
        if e["node"]["name"].startswith(DEPLOY_TOKEN_PREFIX):
            gql("mutation($id:String!){ projectTokenDelete(id:$id) }", {"id": e["node"]["id"]})


def create_deploy_token(project_id, env_id):
    """A project token for the Railway CLI (which rejects workspace tokens).

    Written to DEPLOY_TOKEN_FILE (never to the logs or step outputs) and
    deleted by `--cleanup` at the end of the job, or on the next run.
    """
    delete_deploy_tokens(project_id)
    name = f"{DEPLOY_TOKEN_PREFIX}-{os.environ.get('GITHUB_RUN_ID', 'local')}"
    token = gql(
        "mutation($i:ProjectTokenCreateInput!){ projectTokenCreate(input:$i) }",
        {"i": {"projectId": project_id, "environmentId": env_id, "name": name}},
    )["projectTokenCreate"]
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::add-mask::{token}", flush=True)
    return token


def main():
    if not (os.environ.get("RAILWAY_TOKEN") or os.environ.get("RAILWAY_API_TOKEN")):
        sys.exit("::error::add the RAILWAY_TOKEN secret (repo Settings -> Secrets -> Actions)")
    raw = os.environ.get("CHANGED_FILES", "ALL").strip()
    changed = "ALL" if raw == "ALL" else [line.strip() for line in raw.splitlines() if line.strip()]

    project_id, env_id, (cli_kind, cli_secret) = find_project()
    if "--cleanup" not in sys.argv:
        FIXED["backend"].update(ensure_email())
    if "--cleanup" in sys.argv:
        if AUTH["kind"] == "account":
            delete_deploy_tokens(project_id)
            log("temporary deploy token removed")
        return
    services, status, volumes = load_state(project_id, env_id)
    ensure_services(project_id, env_id, services, volumes)
    ensure_volumes(project_id, env_id, services, volumes)
    ensure_variables(project_id, env_id, services)
    url = ensure_domain(project_id, env_id, services)
    custom_url = ensure_custom_domains(project_id, env_id, services)
    deploy = to_deploy(services, status, changed)

    token_file = os.environ.get("DEPLOY_TOKEN_FILE")
    if token_file:
        if cli_kind == "project":
            token = os.environ[cli_secret]
        else:
            token = create_deploy_token(project_id, env_id)
            log("temporary project token created for the Railway CLI")
        with open(token_file, "w", encoding="utf-8") as fh:
            fh.write(token)

    log(f"deploy: {' '.join(deploy)}")
    log(f"shop:   {url}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"deploy={' '.join(deploy)}\nurl={url}\ncustom_url={custom_url}\n")


if __name__ == "__main__":
    try:
        main()
    except RailwayError as exc:  # shown as an annotation on the run page
        print(f"::error title=Railway setup failed::{exc}", flush=True)
        sys.exit(1)
