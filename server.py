"""fihi-chifae (فيه شفاء) - backend entry point.

Run locally (needs MySQL; see .env.example and docker-compose.yml):
    python server.py [--port 8000] [--open]

The application lives in the ``app`` package (config, db, security, catalog,
orders, sales, account, search, storage, logs, serve). This file only
boots it. In production the nginx frontend serves the pages and images.

API overview (all under /api/v1/; "admin" = HttpOnly session cookie required):
    GET    /ping                              health check
    GET    /catalog                           public catalog, best sellers, delivery settings
    GET    /settings                          shop phone (WhatsApp) + delivery settings
    GET    /search?q=...                      product search (Arabic / French / English)
    POST   /orders                            place an order (public, priced server-side)
    POST   /newsletter                        newsletter sign-up (public)
    GET    /admin/session                     current session (+ username, photo)
    POST   /admin/session                     login (sets the session cookie)
    DELETE /admin/session                     logout
    POST   /admin/reset/request|confirm       password reset by e-mail
    GET|PUT /admin/profile                    username, password, e-mail, phone (admin)
    POST|DELETE /admin/profile/avatar         profile photo (admin)
    GET    /sales/summary                     KPIs + charts (admin)
    GET    /sales/export?month=YYYY-MM        Excel report of confirmed sales (admin)
    GET    /orders?from=&to=&buyer=&all=1     orders with their lines (+ customer summary) (admin)
    GET    /orders/customers?q=               customer names for the orders filter (admin)
    POST   /admin/orders                      manual order, confirmed at once (admin)
    POST   /orders/{id}/confirm|reject        confirm / reject-and-delete (admin)
    POST   /categories, DELETE /categories/{id}        (admin; delete = archive)
    POST   /products, PUT|DELETE /products/{id}        (admin; delete = archive)
    GET    /archive, POST /archive/products/{id}/restore   (admin)
    GET    /admin/backup                      zip: SQL dump + images (admin)
"""

from app.serve import main

if __name__ == "__main__":
    main()
