"""Daily Railway consumption report (run by .github/workflows/railway-usage.yml).

Reads the workspace's billing period, current usage and Railway's own
end-of-period estimate from the public GraphQL API, prices it per service and
compares it with the budget: the Hobby plan's included usage ($5) or the usage
limit set in the Railway dashboard, whichever is relevant.

Environment
-----------
RAILWAY_API_TOKEN     account or workspace token (Railway -> Account -> Tokens).
                      A *project* token cannot read billing.
RAILWAY_WORKSPACE_ID  optional; default: the token's first workspace.
RAILWAY_BUDGET_USD    optional; overrides the budget (default: hard usage limit
                      if set, else the plan's included usage).
RAILWAY_WARN_PCT      warn (and exit 1, so GitHub e-mails you) when the
                      projected bill reaches this % of the budget. Default 80.

Writes a Markdown report to $GITHUB_STEP_SUMMARY (or stdout) and usage.json.
Exit codes: 0 fine, 1 close to / over the budget, 2 API or configuration error.
Standard library only.
"""

import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://backboard.railway.com/graphql/v2"

# Railway list prices (USD), per unit returned by the usage API.
# CPU / RAM / volume are reported per minute; egress in GB.
MONTH_MIN = 30 * 24 * 60
PRICES = {
    "CPU_USAGE": 20.0 / MONTH_MIN,  # $20 per vCPU-month
    "MEMORY_USAGE_GB": 10.0 / MONTH_MIN,  # $10 per GB-month of RAM
    "DISK_USAGE_GB": 0.15 / MONTH_MIN,  # $0.15 per GB-month of volume
    "NETWORK_TX_GB": 0.05,  # $0.05 per GB of egress
}
LABELS = {
    "CPU_USAGE": "CPU",
    "MEMORY_USAGE_GB": "RAM",
    "DISK_USAGE_GB": "Volumes",
    "NETWORK_TX_GB": "Egress",
}
# usage included in the subscription price
INCLUDED_USD = {"HOBBY": 5.0, "PRO": 20.0, "FREE": 1.0}

MEASUREMENTS = list(PRICES)


class ApiError(Exception):
    pass


def gql(token, query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(  # noqa: S310 - fixed https URL
        API,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
            "User-Agent": "fihi-chifae-usage-check",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:  # noqa: S310  # nosec B310
            data = json.loads(res.read())
    except urllib.error.HTTPError as exc:
        raise ApiError(f"HTTP {exc.code}: {exc.read()[:300]!r}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise ApiError(str(exc)) from exc
    if data.get("errors"):
        raise ApiError("; ".join(e.get("message", "?") for e in data["errors"]))
    return data["data"]


WORKSPACES = "query { me { workspaces { id name } } }"

WORKSPACE = """
query($w: String!) {
  workspace(workspaceId: $w) {
    id name plan
    customer {
      currentUsage creditBalance remainingUsageCreditBalance
      billingPeriod { start end }
      usageLimit { softLimit hardLimit isOverLimit }
    }
    projects { edges { node { id name services { edges { node { id name } } } } } }
  }
}
"""

USAGE = """
query($w: String!, $m: [MetricMeasurement!]!, $start: DateTime!, $end: DateTime!) {
  usage(workspaceId: $w, measurements: $m, startDate: $start, endDate: $end,
        groupBy: [PROJECT_ID, SERVICE_ID]) {
    measurement value tags { projectId serviceId }
  }
  estimatedUsage(workspaceId: $w, measurements: $m) { measurement estimatedValue projectId }
}
"""


def money(x):
    return f"${x:,.2f}"


def collect(token, workspace_id=None):
    if not workspace_id:
        spaces = (gql(token, WORKSPACES).get("me") or {}).get("workspaces") or []
        if not spaces:
            raise ApiError("the token sees no workspace (use an account or workspace token)")
        workspace_id = spaces[0]["id"]
    ws = gql(token, WORKSPACE, {"w": workspace_id})["workspace"]
    customer = ws.get("customer") or {}
    period = customer.get("billingPeriod") or {}
    now = dt.datetime.now(dt.timezone.utc)
    start = period.get("start") or now.replace(day=1, hour=0, minute=0, second=0).isoformat()
    end = period.get("end") or now.isoformat()
    data = gql(
        token,
        USAGE,
        {"w": workspace_id, "m": MEASUREMENTS, "start": start, "end": now.isoformat()},
    )
    return ws, customer, start, end, now, data


def analyse(ws, customer, start, end, now, data):
    names = {}
    for p in (ws.get("projects") or {}).get("edges", []):
        node = p["node"]
        names[node["id"]] = node["name"]
        for s in (node.get("services") or {}).get("edges", []):
            names[s["node"]["id"]] = s["node"]["name"]

    per_service, per_kind = {}, dict.fromkeys(MEASUREMENTS, 0.0)
    for row in data.get("usage") or []:
        m = row["measurement"]
        if m not in PRICES:
            continue
        cost = (row.get("value") or 0) * PRICES[m]
        tags = row.get("tags") or {}
        key = (
            names.get(tags.get("projectId"), "?")
            + " / "
            + names.get(tags.get("serviceId"), tags.get("serviceId") or "(volumes, shared)")
        )
        per_service.setdefault(key, dict.fromkeys(MEASUREMENTS, 0.0))[m] += cost
        per_kind[m] += cost
    computed_now = sum(per_kind.values())

    estimated = sum(
        (row.get("estimatedValue") or 0) * PRICES.get(row["measurement"], 0)
        for row in data.get("estimatedUsage") or []
    )
    t0 = dt.datetime.fromisoformat(start.replace("Z", "+00:00"))
    t1 = dt.datetime.fromisoformat(end.replace("Z", "+00:00"))
    elapsed = max((now - t0).total_seconds(), 1)
    total = max((t1 - t0).total_seconds(), elapsed)
    linear = computed_now * total / elapsed
    current = customer.get("currentUsage")
    current = float(current) if current is not None else computed_now
    projected = max(estimated, linear, current)

    plan = (ws.get("plan") or "HOBBY").upper()
    limit = customer.get("usageLimit") or {}
    included = INCLUDED_USD.get(plan, 5.0)
    if os.environ.get("RAILWAY_BUDGET_USD"):
        budget, budget_label = float(os.environ["RAILWAY_BUDGET_USD"]), "RAILWAY_BUDGET_USD"
    elif limit.get("hardLimit"):
        budget, budget_label = float(limit["hardLimit"]), "hard usage limit (dashboard)"
    else:
        budget, budget_label = included, f"{plan.title()} plan included usage"
    warn_pct = float(os.environ.get("RAILWAY_WARN_PCT", "80") or 80)

    return {
        "workspace": ws.get("name"),
        "plan": plan,
        "period": {"start": start, "end": end, "elapsed_pct": round(100 * elapsed / total, 1)},
        "current_usd": round(current, 4),
        "computed_usd": round(computed_now, 4),
        "projected_usd": round(projected, 4),
        "railway_estimate_usd": round(estimated, 4),
        "included_usd": included,
        "budget_usd": budget,
        "budget_source": budget_label,
        "soft_limit": limit.get("softLimit"),
        "hard_limit": limit.get("hardLimit"),
        "over_limit": bool(limit.get("isOverLimit")),
        "credit_balance": customer.get("creditBalance"),
        "warn_pct": warn_pct,
        "used_pct": round(100 * current / budget, 1) if budget else None,
        "projected_pct": round(100 * projected / budget, 1) if budget else None,
        "by_kind": {LABELS[k]: round(v, 4) for k, v in per_kind.items()},
        "by_service": {
            k: {LABELS[m]: round(c, 4) for m, c in v.items()}
            for k, v in sorted(per_service.items(), key=lambda kv: -sum(kv[1].values()))
        },
    }


def report(r):
    status = "🟢 OK"
    if r["over_limit"] or (r["projected_pct"] or 0) >= 100:
        status = "🔴 Over budget (projected)"
    elif (r["projected_pct"] or 0) >= r["warn_pct"]:
        status = f"🟠 Close to the budget (≥ {r['warn_pct']:.0f} %)"
    lines = [
        f"## Railway usage — {r['workspace']} ({r['plan'].title()} plan)",
        "",
        f"**Status: {status}**",
        "",
        "| | |",
        "|---|---|",
        f"| Billing period | {r['period']['start'][:10]} → {r['period']['end'][:10]}"
        f" ({r['period']['elapsed_pct']} % elapsed) |",
        f"| Usage so far | **{money(r['current_usd'])}** ({r['used_pct']} % of budget) |",
        f"| Projected end of period | **{money(r['projected_usd'])}**"
        f" ({r['projected_pct']} % of budget) |",
        f"| Budget | {money(r['budget_usd'])} — {r['budget_source']} |",
        f"| Included in the plan | {money(r['included_usd'])} |",
    ]
    if r["hard_limit"] or r["soft_limit"]:
        lines.append(
            f"| Usage limits (dashboard) | soft {r['soft_limit'] or '—'}"
            f" / hard {r['hard_limit'] or '—'} |"
        )
    if r["credit_balance"] is not None:
        lines.append(f"| Credit balance | {money(float(r['credit_balance']))} |")
    lines += [
        "",
        "### By resource (so far)",
        "",
        "| " + " | ".join(r["by_kind"]) + " |",
        "|" + "---|" * len(r["by_kind"]),
        "| " + " | ".join(money(v) for v in r["by_kind"].values()) + " |",
        "",
        "### By service (so far)",
        "",
        "| Project / service | " + " | ".join(LABELS.values()) + " | Total |",
        "|---|" + "---|" * (len(LABELS) + 1),
    ]
    for name, costs in r["by_service"].items():
        lines.append(
            f"| {name} | "
            + " | ".join(money(costs[label]) for label in LABELS.values())
            + f" | **{money(sum(costs.values()))}** |"
        )
    lines += [
        "",
        "_Costs are computed from Railway's list prices (CPU $20/vCPU-month, RAM $10/GB-month,"
        " volumes $0.15/GB-month, egress $0.05/GB); the dashboard's invoice is authoritative._",
    ]
    return "\n".join(lines) + "\n", status


def main():
    token = os.environ.get("RAILWAY_API_TOKEN", "").strip()
    if not token:
        print("::error::Set the RAILWAY_API_TOKEN secret (Railway → Account → Tokens).")
        return 2
    try:
        r = analyse(*collect(token, os.environ.get("RAILWAY_WORKSPACE_ID", "").strip() or None))
    except ApiError as exc:
        print(f"::error::Railway API: {exc}")
        return 2
    md, status = report(r)
    with open("usage.json", "w", encoding="utf-8") as fh:
        json.dump(r, fh, indent=2)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(md)
    print(md)
    msg = (
        f"Railway: {money(r['current_usd'])} used, {money(r['projected_usd'])} projected"
        f" of {money(r['budget_usd'])} ({r['projected_pct']} %)"
    )
    if status.startswith("🟢"):
        print(f"::notice::{msg}")
        return 0
    print(f"::{'error' if status.startswith('🔴') else 'warning'}::{msg}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
