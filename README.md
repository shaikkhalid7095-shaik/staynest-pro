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
