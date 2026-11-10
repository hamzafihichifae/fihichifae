"""Prepare the Railway project so a deploy leaves a working shop. Idempotent.

Run by the CI/CD deploy job before every deploy. It only adds what is missing:

* the five services (mysql, storage, search, backend, frontend), each building
  its own Dockerfile / railway.json;
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

# name -> (railway.json, Dockerfile, volume mount or None, folder that triggers a redeploy)
SERVICES = {
    "mysql": (
        "deploy/mysql/railway.json",
        "deploy/mysql/Dockerfile",
        "/var/lib/mysql",
        "deploy/mysql/",
    ),
    "storage": (
        "deploy/garage/railway.json",
        "deploy/garage/Dockerfile",
        "/var/lib/garage",
        "deploy/garage/",
    ),
    "search": (
        "deploy/search/railway.json",
        "deploy/search/Dockerfile",
        "/meili_data",
        "deploy/search/",
    ),
    "backend": ("railway.json", "Dockerfile", None, None),
    "frontend": ("deploy/frontend/railway.json", "deploy/frontend/Dockerfile", None, None),
}
ORDER = ["mysql", "storage", "search", "backend", "frontend"]
INFRA = {"mysql", "storage", "search"}
FRONTEND_PORT = 8080


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
        "FIHI_PUBLIC_BASE_URL": "https://${{frontend.RAILWAY_PUBLIC_DOMAIN}}",
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


def gql(query, variables=None, project_token=None):
    token = project_token or os.environ["RAILWAY_API_TOKEN"]
    headers = {"Content-Type": "application/json", "User-Agent": "fihi-chifae-bootstrap"}
    if project_token:
        headers["Project-Access-Token"] = token
    else:
        headers["Authorization"] = "Bearer " + token
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


def find_project():
    data = gql(
        "{ projectToken { projectId environmentId } }", project_token=os.environ["RAILWAY_TOKEN"]
    )
    return data["projectToken"]["projectId"], data["projectToken"]["environmentId"]


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
        cfg, dockerfile, _mount, _folder = SERVICES[name]
        gql(
            """mutation($s:String!,$e:String!,$i:ServiceInstanceUpdateInput!){
              serviceInstanceUpdate(serviceId:$s, environmentId:$e, input:$i) }""",
            {
                "s": services[name],
                "e": env_id,
                "i": {"railwayConfigFile": cfg, "dockerfilePath": dockerfile},
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
    sid = services["frontend"]
    q = """query($p:String!,$e:String!,$s:String!){
      domains(projectId:$p, environmentId:$e, serviceId:$s){
        serviceDomains { domain } customDomains { domain } } }"""
    d = gql(q, {"p": project_id, "e": env_id, "s": sid})["domains"]
    names = [x["domain"] for x in d["customDomains"] + d["serviceDomains"]]
    if not names:
        data = gql(
            "mutation($i:ServiceDomainCreateInput!){ serviceDomainCreate(input:$i){ domain } }",
            {"i": {"environmentId": env_id, "serviceId": sid, "targetPort": FRONTEND_PORT}},
        )
        names = [data["serviceDomainCreate"]["domain"]]
        log(f"+ public domain {names[0]}")
    return "https://" + names[0]


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


def main():
    for var in ("RAILWAY_TOKEN", "RAILWAY_API_TOKEN"):
        if not os.environ.get(var):
            sys.exit(f"::error::missing secret {var} (repo Settings -> Secrets -> Actions)")
    raw = os.environ.get("CHANGED_FILES", "ALL").strip()
    changed = "ALL" if raw == "ALL" else [line.strip() for line in raw.splitlines() if line.strip()]

    project_id, env_id = find_project()
    services, status, volumes = load_state(project_id, env_id)
    ensure_services(project_id, env_id, services, volumes)
    ensure_volumes(project_id, env_id, services, volumes)
    ensure_variables(project_id, env_id, services)
    url = ensure_domain(project_id, env_id, services)
    deploy = to_deploy(services, status, changed)

    log(f"deploy: {' '.join(deploy)}")
    log(f"shop:   {url}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"deploy={' '.join(deploy)}\nurl={url}\n")


if __name__ == "__main__":
    main()
