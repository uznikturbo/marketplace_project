# Marketplace

[![CI](https://github.com/uznikturbo/marketplace_project/actions/workflows/ci.yml/badge.svg)](https://github.com/uznikturbo/marketplace_project/actions/workflows/ci.yml)

A full-stack e-commerce marketplace built with Django. It ships with a
storefront, a guest-friendly cart, checkout with delivery and payment
options, a vendor dashboard, SMS phone verification, and integrations with
Nova Poshta and LiqPay.

The UI is server-rendered (Django templates) with no separate frontend
build step.

---

## Table of contents

- [Features](#features)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [Environment variables](#environment-variables)
- [Running the tests](#running-the-tests)
- [Linting and coverage](#linting-and-coverage)
- [How the main flows work](#how-the-main-flows-work)
- [Secret key rotation](#secret-key-rotation)
- [Security notes](#security-notes)
- [Known limitations](#known-limitations)

---

## Features

### Storefront

- Product catalog with search, category filtering (including nested
  categories), sorting, grid/list view and caching of category trees.
- Promotions, new arrivals and top sales pages built on the catalog with
  preset filters and ordering.
- Product pages with average rating, reviews and active discounts.
- Wishlist for both authenticated users and guests (session based).
- Responsive templates with an inline design system.
- Static information pages (company, delivery, warranty, partners,
  support) linked from the header and footer.

### Cart and checkout

- Cart for authenticated users and guests; the guest cart is merged into
  the user cart on login.
- Quantity is validated against available stock on every operation.
- Checkout validates the cart, re-checks stock inside a transaction with
  `select_for_update`, and rolls the whole order back if anything fails.
- Order items keep a price snapshot, so later price changes do not alter
  historical orders.
- Cash-on-delivery fee is calculated as `20 UAH + 2%` of the cart total.

### Payments

- LiqPay integration (sandbox and production) with a signed redirect and
  a server callback.
- The callback verifies the signature with `hmac.compare_digest`, handles
  malformed payloads, ignores unknown orders, and never downgrades an
  already paid order.
- Payment flows are disabled gracefully when keys are not configured.

### Delivery

- Nova Poshta city and warehouse lookup proxied through the backend, with
  request timeouts and error handling.
- Branch, parcel locker and courier delivery options.

### Accounts

- Phone number as the login identifier, with normalization to
  `+380XXXXXXXXX` and case-insensitive e-mail uniqueness.
- Registration, login with a safe `next` redirect, and logout.
- SMS confirmation of the phone number with a resend cooldown, a limit of
  five verification attempts and a fresh code invalidating the counter.
- Profile editing, order history and wishlist pages.

### Vendors

- Vendor-only dashboard protected by a dedicated decorator.
- Product CRUD with an image formset; vendors can only touch their own
  products.
- Discount management with validation of percentage and date range.
- Vendor order list with revenue statistics and status updates.

### Operations

- `/health` endpoint that checks the database and returns `200`/`503` JSON.
- `/favicon.ico` served directly by the application.
- Optional automatic rotation of the Django `SECRET_KEY` via Celery beat.
- Django admin customized with Jazzmin.
- Celery worker for background SMS delivery.

---

## Tech stack

| Layer            | Technology                                  |
| ---------------- | ------------------------------------------- |
| Language         | Python 3.12+                                |
| Framework        | Django 6.0                                  |
| Database         | PostgreSQL (`psycopg2-binary`)              |
| Cache            | Redis                                       |
| Background jobs  | Celery + Redis                              |
| Static files     | WhiteNoise                                  |
| Admin theme      | django-jazzmin                              |
| Phone numbers    | django-phonenumber-field                    |
| Payments         | LiqPay                                      |
| Delivery         | Nova Poshta API                             |
| Configuration    | python-dotenv                               |
| WSGI server      | Gunicorn                                    |
| CI               | GitHub Actions                              |

---

## Project structure

```text
rozetka2.0/
├── .env.example              # documented environment template
├── .github/workflows/ci.yml  # GitHub Actions pipeline
├── requirements.txt          # pinned runtime dependencies
├── requirements-dev.txt      # runtime + Debug Toolbar + Playwright
├── README.md
├── .venv/                    # local virtualenv (not tracked)
└── marketplace/
    ├── manage.py
    ├── marketplace/          # project configuration
    │   ├── settings/         # base / dev / prod / test modules
    │   ├── urls.py
    │   ├── celery.py
    │   ├── wsgi.py
    │   └── asgi.py
    ├── catalog/              # products, categories, cart, favorites, reviews
    ├── orders/               # checkout, orders, LiqPay, Nova Poshta
    ├── users/                # custom user model, profile, SMS verification
    ├── registration/         # sign-up, login, SMS task and code generation
    ├── vendors/              # vendor dashboard and product management
    ├── core/                 # home page, health check, middleware, favicon,
    │                         # secret key rotation task and command
    ├── templates/            # shared templates
    ├── static/               # source static assets
    └── tests/                # test suite (203 tests)
```

Each app owns its models, views, URLs and templates. Shared helpers live in
`catalog/utils.py` and `core/`.

### Frontend structure

The UI is server-rendered with Django templates and has no build step. Shared
pieces are plain `{% include %}` partials (files prefixed with `_`) so the same
markup and CSS are defined once:

| Partial | Used by | Purpose |
| --- | --- | --- |
| `vendors/_sidebar.html` | all vendor pages | Seller Hub navigation (`active`, `show_orders`, `show_back`) |
| `vendors/_product_form_fields.html` | create/edit product | image formset + dynamic characteristics |
| `vendors/_product_form_js.html` | create/edit product | formset and JSON `properties` logic (`edit_mode`) |
| `users/_profile_sidebar.html` | profile, orders, wishlist | user card + navigation (`active`) |
| `users/_profile_nav.html` | profile pages | profile menu links |
| `catalog/_wishlist_empty.html` | both wishlist pages | empty-state block |
| `*/_styles_*.html` | 2–6 pages each | verbatim shared CSS rules |

`core/base.html` holds the design tokens, header, footer and global styles;
page-specific CSS lives in a `{% block extra_css %}` on each page.

---

## Getting started

### Prerequisites

- Python 3.12 or newer
- PostgreSQL 14+
- Redis 6+ (cache and Celery broker)
- A virtualenv tool (`venv` is enough)

### 1. Clone and create a virtualenv

```bash
git clone https://github.com/uznikturbo/marketplace_project.git
cd rozetka2.0
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

`requirements.txt` contains runtime dependencies only; `requirements-dev.txt`
adds the Debug Toolbar, Playwright, Ruff and coverage for local development,
linting and tests.

### 2. Configure the environment

```bash
cp .env.example .env
```

Open `.env` and set at least:

- `DJANGO_SECRET_KEY` — generate one with:
  ```bash
  python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
  ```
- `POSTGRES_PASSWORD`

`manage.py` uses `marketplace.settings.dev` by default, so local development
does not require a secret key (an insecure fallback is used). Production
settings require `DJANGO_SECRET_KEY` (or a rotated key file) and refuse to
start without it.

### Settings modules

| Module                   | Used by                     | Behaviour                                              |
| ------------------------ | --------------------------- | ------------------------------------------------------ |
| `marketplace.settings.dev`  | `manage.py` (default)    | `DEBUG=True`, Debug Toolbar, plain HTTP                |
| `marketplace.settings.prod` | WSGI, ASGI, Celery       | `DEBUG=False`, HTTPS redirect, HSTS, secure cookies    |
| `marketplace.settings.test` | tests and CI             | in-memory cache, fast hasher, no HTTPS enforcement     |

Override the module with `DJANGO_SETTINGS_MODULE`, for example:

```bash
DJANGO_SETTINGS_MODULE=marketplace.settings.prod python manage.py check --deploy
```

### 3. Create the database

```bash
sudo -u postgres psql -c "CREATE USER myuser WITH PASSWORD 'your-password' CREATEDB;"
sudo -u postgres psql -c "CREATE DATABASE marketplace_db OWNER myuser;"
```

`CREATEDB` is required because Django creates a separate test database.

### 4. Apply migrations

```bash
cd marketplace
python manage.py migrate
```

### 5. Start Redis (if it is not running)

```bash
redis-server
```

### 6. Run the application

```bash
cd marketplace
python manage.py runserver
```

Open <http://127.0.0.1:8000/>.

Create an administrator:

```bash
python manage.py createsuperuser
```

The admin panel is available at <http://127.0.0.1:8000/admin/>.

### 7. Run the Celery worker and beat (optional)

SMS messages are sent in the background, and a periodic task rotates the
Django secret key. Without a worker the tasks are queued but never executed;
without beat the periodic schedule is never triggered.

```bash
cd marketplace
celery -A marketplace worker -l info
celery -A marketplace beat -l info
```

If `SMS_API_URL` is empty, the task writes the confirmation code to the
worker log instead of sending an SMS, which is convenient for local
development.

---

## Environment variables

All variables are read in `marketplace/settings/base.py` via `python-dotenv`.
See `.env.example` for a ready-to-copy template.

| Variable                      | Required | Default                              | Description                                              |
| ----------------------------- | -------- | ------------------------------------ | -------------------------------------------------------- |
| `DJANGO_SETTINGS_MODULE`      | no       | dev for `manage.py`, prod for WSGI   | Settings module (see above).                             |
| `DJANGO_SECRET_KEY`           | yes\*    | —                                    | Django secret key. Required by `settings.prod`.          |
| `DJANGO_ALLOWED_HOSTS`        | no       | `localhost,127.0.0.1`                | Comma-separated `ALLOWED_HOSTS`. Dev adds ngrok domains. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | no       | empty                                | Comma-separated trusted origins. Dev adds ngrok.         |
| `POSTGRES_DB`                 | no       | `marketplace_db`                     | Database name.                                           |
| `POSTGRES_USER`               | no       | `myuser`                             | Database user.                                           |
| `POSTGRES_PASSWORD`           | yes      | —                                    | Database password.                                       |
| `POSTGRES_HOST`               | no       | `localhost`                          | Database host.                                           |
| `POSTGRES_PORT`               | no       | `5432`                               | Database port.                                           |
| `REDIS_CACHE_URL`             | no       | `redis://127.0.0.1:6379/1`           | Redis URL used for the cache.                            |
| `CELERY_BROKER_URL`           | no       | `redis://127.0.0.1:6379/0`           | Celery broker URL.                                       |
| `CELERY_RESULT_BACKEND`       | no       | value of `CELERY_BROKER_URL`         | Celery result backend.                                   |
| `NOVAPOST_API`                | no       | empty                                | Nova Poshta API key. Lookup endpoints return 503 if unset.|
| `LIQPAY_PUBLIC_KEY`           | no       | empty                                | LiqPay public key. Online payment is disabled if unset.  |
| `LIQPAY_PRIVATE_KEY`          | no       | empty                                | LiqPay private key, used for signatures.                 |
| `SMS_API_URL`                 | no       | empty                                | SMS provider endpoint. Codes are logged when unset.      |
| `SMS_API_KEY`                 | no       | empty                                | SMS provider API key.                                    |
| `DJANGO_SECRET_KEY_FILE`      | no       | `marketplace/.secret_key`            | File used by the rotation task. Overrides `DJANGO_SECRET_KEY` when present. |
| `SECRET_KEY_ROTATION_DAYS`    | no       | `7`                                  | Rotate the secret key every N days. `0` disables rotation. |
| `DJANGO_SECURE_SSL_REDIRECT`  | no       | `True` (prod)                        | Redirect HTTP to HTTPS.                                  |
| `DJANGO_SECURE_HSTS_SECONDS`  | no       | `31536000` (prod)                    | HSTS max-age in seconds. `0` disables HSTS.              |
| `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` | no | `True` (prod)                     | Apply HSTS to subdomains.                                |
| `DJANGO_SECURE_HSTS_PRELOAD`  | no       | `True` (prod)                        | Allow HSTS preload list submission.                      |
| `DJANGO_SESSION_COOKIE_SECURE`| no       | `True` (prod)                        | Send the session cookie over HTTPS only.                 |
| `DJANGO_CSRF_COOKIE_SECURE`   | no       | `True` (prod)                        | Send the CSRF cookie over HTTPS only.                    |

\* Required by `marketplace.settings.prod`.

---

## Running the tests

The suite contains **225 tests**: 209 unit/integration tests and 16 browser
end-to-end tests. It does not require Redis: `marketplace.settings.test`
switches to an in-memory cache and a fast password hasher. Browser tests need
Playwright (see below); without it they are skipped.

```bash
cd marketplace
python manage.py test
```

Useful variants:

```bash
# one module
python manage.py test tests.test_orders

# one class or test
python manage.py test tests.test_orders.CheckoutTests
python manage.py test tests.test_orders.CheckoutTests.test_postpaid_order_is_created

# verbose
python manage.py test -v 2
```

Test modules:

| Module                     | What it covers                                                        |
| -------------------------- | --------------------------------------------------------------------- |
| `tests/test_models.py`     | Phone/e-mail normalization, uniqueness, ratings, prices, discounts, cart totals |
| `tests/test_catalog.py`    | Catalog, search, sorting, promotions/new/top pages, reviews, cart rules, favorites |
| `tests/test_orders.py`     | Checkout, stock rollback, payments, LiqPay callback, Nova Poshta        |
| `tests/test_users.py`      | Profile, order history, SMS send/verify limits                         |
| `tests/test_vendors.py`    | Vendor access, product ownership, discounts, vendor orders             |
| `tests/test_registration.py` | Registration, login and `next` safety, SMS task behavior            |
| `tests/test_core.py`       | Home page, info pages, header/footer links, health check, favicon, timezone |
| `tests/test_secret_rotation.py` | Secret key file creation, permissions, task and management command |
| `tests/test_ui.py`         | Playwright/Firefox: home, catalog, cart, login, profile, vendor form   |

> The test database is created and destroyed automatically. The database
> user therefore needs the `CREATEDB` privilege.

### Browser (UI) tests

The UI suite drives headless **Firefox** through Playwright and checks the
rendered HTML, inline CSS and inline JavaScript together.

```bash
pip install -r requirements-dev.txt
python -m playwright install firefox

cd marketplace
python manage.py test tests.test_ui
```

Run only the fast unit/integration suite (skips the browser tests):

```bash
python manage.py test --exclude-tag=ui
```

If Playwright or its Firefox build is missing, the UI tests are skipped. Set
`UI_TESTS_REQUIRED=1` to turn that skip into a failure; CI uses this to make
sure the browser suite really runs.

### Linting and coverage

Ruff and coverage are configured in `marketplace/pyproject.toml` and installed
by `requirements-dev.txt`.

```bash
cd marketplace

# lint
ruff check .

# unit/integration tests with branch coverage
coverage run manage.py test --exclude-tag=ui
coverage report
```

Coverage fails below 88% (`fail_under` in `pyproject.toml`). The HTML report is
available with `coverage html` (`htmlcov/` is gitignored). CI runs both `ruff`
and the coverage command on every push and pull request.

---

## How the main flows work

### Guest cart and login

A guest cart is stored with the session key. Before `login()` rotates the
session, the original key is saved in `request.session["cart_session_key"]`,
so the `user_logged_in` signal can find the guest cart, merge its items into
the user cart and delete the guest one.

### Checkout

1. The cart is validated (must exist and be non-empty).
2. The form is validated.
3. Inside `transaction.atomic()` every product is locked with
   `select_for_update`, availability and stock are re-checked, `OrderItem`
   rows are created with a price snapshot, and stock is decremented.
4. The cart is cleared and the order id is stored in the session for guests.
5. LiqPay orders are redirected to a signed payment page; cash-on-delivery
   orders go straight to the success page.

### LiqPay callback

`POST /orders/liqpay-callback/` receives `data` and `signature`:

- the signature is verified as `base64(sha1(private_key + data + private_key))`
  using a constant-time comparison;
- the payload is decoded and validated;
- `success`, `wait_accept` and `sandbox` mark the order as paid and move it
  to processing;
- `failure` and `error` mark it as failed, unless it is already paid;
- unknown orders return `404`, malformed requests return `400`.

### SMS verification

- A six-digit code is generated with `secrets`, stored in the cache for five
  minutes and sent by a Celery task.
- Resending is blocked for 60 seconds.
- Five wrong attempts block verification until a new code is requested.
- If the broker is unavailable, the endpoint returns `503` and clears the
  cooldown so the user is not locked out.

---

## Secret key rotation

Django's `SECRET_KEY` signs sessions, CSRF tokens and password-reset links.
Rotating it invalidates all of them, which means every rotation logs users
out and breaks links that were issued before it.

The project can rotate the key automatically with a Celery beat task:

- the key is stored in `SECRET_KEY_FILE` (default `marketplace/.secret_key`),
  created with `0600` permissions and ignored by git;
- a key file takes precedence over `DJANGO_SECRET_KEY`, so the first rotation
  switches the application to file-based storage;
- `core.tasks.rotate_secret_key_task` is scheduled every
  `SECRET_KEY_ROTATION_DAYS` days (default `7`; set `0` to disable);
- the file is replaced atomically, so a crash cannot leave a partial key.

Manual rotation:

```bash
cd marketplace
python manage.py rotate_secret_key
```

**Important:** Django reads `SECRET_KEY` once at startup. After a rotation
the running web and worker processes keep the old key until they are
restarted (for Gunicorn, `kill -HUP <master-pid>` is enough). Plan the
restart for a low-traffic moment: as soon as the new key is loaded, all
existing sessions and signed links become invalid.

Because rotation logs everyone out, a short interval is a trade-off between
security and user experience. Set `SECRET_KEY_ROTATION_DAYS=0` if that is
not acceptable for your deployment.

With multiple application instances the key file must live on shared storage
(or be replaced by a proper secret manager); otherwise instances end up with
different keys and reject each other's sessions.

---

## Security notes

- Secrets are read from environment variables; `.env` is git-ignored.
- All state-changing cart endpoints are `POST`-only and CSRF-protected.
- Order pages and payment pages enforce ownership (no IDOR).
- Guest orders are visible only from the session that created them.
- Login redirects use `url_has_allowed_host_and_scheme`.
- Payment callbacks are signature-checked with `hmac.compare_digest`.
- Passwords are hashed with Django's default hasher; the test suite uses a
  faster one for speed only.

Before deploying:

- set a strong `DJANGO_SECRET_KEY` and real `DJANGO_ALLOWED_HOSTS`;
- use `marketplace.settings.prod` (WSGI/ASGI already default to it);
- make sure the reverse proxy sends `X-Forwarded-Proto: https`;
- run `python manage.py check --deploy` with the production settings;
- run `python manage.py collectstatic`;
- serve the app with Gunicorn behind a reverse proxy.

`settings.prod` enables `SECURE_SSL_REDIRECT`, HSTS, `SESSION_COOKIE_SECURE`,
`CSRF_COOKIE_SECURE`, `X_FRAME_OPTIONS=DENY` and `SECURE_CONTENT_TYPE_NOSNIFF`.
They can be relaxed through environment variables while TLS is being set up.

---

## Known limitations

- No API layer (DRF); everything is server-rendered.
- Automatic secret rotation only takes effect after a process restart, and
  needs shared storage when running several instances.
- Full-text search uses `icontains`; a PostgreSQL trigram index would make it
  scale better.
- Payment and SMS integrations are tested with mocks; no sandbox end-to-end
  tests are included.

---

## License

This project was built for learning and portfolio purposes.
