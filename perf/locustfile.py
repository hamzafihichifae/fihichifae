"""Load profile for fihi-chifae (run by perf/run.sh and the CI "Performance" job).

Two kinds of virtual users, mimicking real traffic:

- ``Shopper`` (the crowd): opens the shop, loads the catalog, reads the info
  page, now and then places an order with delivery details.
- ``Admin`` (exactly one): logs in once, then keeps the dashboard, the orders
  list and the archive refreshed like the owner would.

Run against a disposable server only - shoppers really create orders.
"""

import os
import random

from locust import HttpUser, between, events, task

ADMIN_USER = os.environ.get("PERF_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("PERF_ADMIN_PASSWORD", "perf-admin-pass")
CITIES = ["Fès", "BHALIL", "Sefrou", "Meknès", "Casablanca", "Rabat"]

_catalog = {"products": []}


@events.test_start.add_listener
def _load_catalog(environment, **_kw):
    """Fetch the product list once so orders reference real products."""
    import requests

    data = requests.get(environment.host + "/api/v1/catalog", timeout=10).json()
    _catalog["products"] = [
        {"id": p["id"], "sizes": [s["size"] + s["unit"] for s in p.get("sizes", [])]}
        for c in data.get("categories", [])
        for p in c.get("products", [])
        if p.get("sizes")
    ]


class Shopper(HttpUser):
    weight = 20
    wait_time = between(1, 4)  # think time between page actions

    def on_start(self):
        self.visit_home()

    @task(6)
    def visit_home(self):
        self.client.get("/", name="GET / (page)")
        self.client.get("/api/v1/catalog", name="GET /api/v1/catalog")

    @task(3)
    def static_assets(self):
        # a returning browser revalidates its cached files (304 when unchanged)
        for path in ("/assets/style.css?v=9", "/assets/main.js?v=18", "/media/logo.jpg"):
            self.client.get(path, name="GET /assets/* (static)")

    @task(2)
    def search(self):
        query = random.choice(["miel", "honey", "عسل", "زيت أركان", "huile", "the", "amlou", "parfum"])
        self.client.get("/api/v1/search", params={"q": query}, name="GET /api/v1/search")

    @task(1)
    def info_page(self):
        self.client.get("/info.html", name="GET /info.html (page)")

    @task(1)
    def place_order(self):
        if not _catalog["products"]:
            return
        lines = []
        for p in random.sample(_catalog["products"], k=min(2, len(_catalog["products"]))):
            lines.append({"id": p["id"], "size": random.choice(p["sizes"]), "qty": 1})
        order = {
            "buyer": "Perf Test",
            "phone": "06" + str(random.randint(10000000, 99999999)),
            "address": "Load test street 1",
            "city": random.choice(CITIES),
            "items": lines,
        }
        self.client.post("/api/v1/orders", json=order, name="POST /api/v1/orders")


class Admin(HttpUser):
    fixed_count = 1  # one shop owner, whatever the crowd size
    wait_time = between(2, 5)

    def on_start(self):
        res = self.client.post(
            "/api/v1/admin/session",
            json={"username": ADMIN_USER, "password": ADMIN_PASSWORD},
            name="POST /api/v1/admin/session (login)",
        )
        # The production cookie is "Secure" (HTTPS only); the test server is
        # plain HTTP, so forward the token explicitly.
        token = res.cookies.get("fc_session")
        if token:
            self.client.headers["Cookie"] = f"fc_session={token}"

    @task(3)
    def dashboard(self):
        self.client.get("/api/v1/sales/summary", name="GET /api/v1/sales/summary (admin)")

    @task(3)
    def orders(self):
        self.client.get("/api/v1/orders", name="GET /api/v1/orders (admin)")

    @task(1)
    def archive(self):
        self.client.get("/api/v1/archive", name="GET /api/v1/archive (admin)")
