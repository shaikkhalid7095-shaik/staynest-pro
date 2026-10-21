# StayNest Pro - Hotel Booking Backend

Backend API for a hotel and resort booking platform, built with FastAPI and MySQL.
Customers search and book hotels, hotel owners manage hotels, rooms and staff,
and admins approve hotels and watch the whole platform.

## Tech stack

- Python, FastAPI, Uvicorn
- MySQL 8+, SQLAlchemy 2.0, Alembic
- Pydantic v2
- JWT login (30 min access token, 7 day refresh token), bcrypt passwords
- Stripe for payments (mock mode available)
- pytest for tests

## Numbers

- 50 modules complete
- 153 API endpoints
- 40 database tables
- 62 automated tests (all passing)

## Roles

- CUSTOMER - search, book, pay, review, wishlist, loyalty points
- HOTEL_OWNER - hotels, room types, rooms, pricing, staff, reports
- HOTEL_STAFF - check-in / check-out, housekeeping
- ADMIN - approve hotels, users, plans, coupons, platform settings

## Main features

- Register, login, refresh, logout, email verify, forgot / reset password
- Account lock after too many failed logins
- Hotels, room types, rooms, amenities, gallery
- Search hotels by city, dates, price and rating
- Bookings with 15 minute payment hold, GST (12% up to Rs 7500 per night, 18% above)
- Payments, refunds and invoices
- Coupons, seasonal pricing, subscription plans for owners
- Reviews, wishlist, notifications, messages
- Check-in, check-out, housekeeping
- Owner analytics and admin reports
- Audit log and fraud flags

## Setup (Windows)

    git clone https://github.com/shaikkhalid7095-shaik/staynest-pro.git
    cd staynest-pro
    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt

1. Create the database in MySQL: `CREATE DATABASE staynest_db;`
2. Copy `.env.example` to `.env` and fill in your MySQL password and a secret key
3. Create the tables: `alembic upgrade head`
4. Add roles, plans and the admin user: `python -m app.db.seed`
5. Start the server: `uvicorn app.main:app --reload`

Open Swagger at http://127.0.0.1:8000/docs

## Payments without a Stripe account

Stripe sign-up in India is invite-only, so the project has a mock mode.
With `STRIPE_MOCK=True` in `.env`, payments use `app/core/fake_stripe.py`
instead of stripe.com. Payment ids look like `pi_mock_...`.
To use real Stripe, set `STRIPE_MOCK=False` and add your `sk_test_...` key.
No code change is needed.

With `DEBUG=True`, `POST /payments/{payment_id}/test-confirm` marks a payment as paid.

## Run tests

    python -m pytest -v

The tests use an in-memory SQLite database, so MySQL is not touched.

## Check modules

    python check_modules.py

## Project structure

    app/
      core/       config, security, fake_stripe
      db/         database session, seed
      models/     SQLAlchemy tables
      schemas/    Pydantic request / response models
      services/   business logic
      routers/    API endpoints
    alembic/      database migrations
    tests/        pytest tests

## Author

Shaik Zunaid - https://github.com/shaikkhalid7095-shaik
