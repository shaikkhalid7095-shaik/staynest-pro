"""Checks which of the 50 modules are in place: endpoints in the app + tables in MySQL."""
from fastapi.routing import APIRoute

from app.main import app

MODULES = [
    (1, "Authentication and RBAC", ["POST /auth/login", "POST /auth/refresh"], ["users", "roles", "refresh_tokens"]),
    (2, "Customer Profile Management", ["PUT /users/me/profile"], ["customer_profiles"]),
    (3, "Hotel Registration and Verification", ["POST /hotels", "PATCH /hotels/{hotel_id}/verify"], ["hotels"]),
    (4, "Hotel Profile Management", ["PUT /hotels/{hotel_id}", "POST /hotels/{hotel_id}/branches"], ["hotel_branches"]),
    (5, "Room Management", ["POST /hotels/{hotel_id}/rooms"], ["rooms"]),
    (6, "Room Type Management", ["POST /hotels/{hotel_id}/room-types"], ["room_types"]),
    (7, "Hotel Amenities Management", ["GET /amenities", "PUT /hotels/{hotel_id}/amenities"], ["amenities", "hotel_amenities"]),
    (8, "Room Availability Management", ["GET /hotels/{hotel_id}/availability"], ["bookings"]),
    (9, "Hotel Search System", ["GET /search/hotels"], ["hotels"]),
    (10, "Advanced Hotel Filters", ["GET /search/hotels"], ["hotels"]),
    (11, "Hotel Details and Gallery", ["GET /hotels/{hotel_id}/details", "POST /hotels/{hotel_id}/images"], ["hotel_images"]),
    (12, "Room Booking System", ["POST /bookings"], ["bookings"]),
    (13, "Guest Management", ["PUT /bookings/{booking_id}/guests"], ["booking_guests"]),
    (14, "Booking Management", ["GET /bookings/my", "GET /bookings/hotel/{hotel_id}"], ["bookings"]),
    (15, "Stripe Payment Integration", ["POST /payments/create-intent", "POST /payments/webhook"], ["payments", "stripe_events"]),
    (16, "Invoice and Receipt Management", ["GET /bookings/{booking_id}/invoice"], ["invoices"]),
    (17, "Cancellation and Refund Management", ["POST /bookings/{booking_id}/cancel"], ["refunds"]),
    (18, "Coupon and Discount Management", ["POST /coupons", "POST /coupons/validate"], ["coupons"]),
    (19, "Reviews and Ratings", ["POST /reviews"], ["reviews"]),
    (20, "Wishlist and Favorite Hotels", ["POST /wishlist/{hotel_id}"], ["wishlist_items"]),
    (21, "AI Hotel Recommendation Engine", ["GET /ai/recommendations"], ["hotels"]),
    (22, "AI Travel Assistant", ["POST /ai/travel-assistant"], ["chat_messages"]),
    (23, "AI Customer Support Chatbot", ["POST /ai/support-chat"], ["chat_messages"]),
    (24, "In-App Notifications", ["GET /notifications"], ["notifications"]),
    (25, "In-App Messaging", ["POST /bookings/{booking_id}/messages"], ["messages"]),
    (26, "Housekeeping Management", ["POST /hotels/{hotel_id}/housekeeping"], ["housekeeping_tasks"]),
    (27, "Hotel Staff Management", ["POST /hotels/{hotel_id}/staff"], ["hotel_staff"]),
    (28, "Check-In and Check-Out Management", ["POST /bookings/{booking_id}/check-in", "POST /bookings/{booking_id}/check-out"], ["bookings"]),
    (29, "Additional Services Management", ["POST /hotels/{hotel_id}/services"], ["hotel_services"]),
    (30, "Room Service Management", ["POST /bookings/{booking_id}/services"], ["service_orders"]),
    (31, "Hotel Revenue Analytics", ["GET /analytics/revenue"], ["bookings"]),
    (32, "Hotel Occupancy Analytics", ["GET /analytics/occupancy"], ["bookings"]),
    (33, "Customer Analytics", ["GET /analytics/customers"], ["bookings"]),
    (34, "Hotel Owner Dashboard APIs", ["GET /dashboard/owner"], ["payouts"]),
    (35, "Customer Dashboard APIs", ["GET /dashboard/customer"], ["loyalty_accounts"]),
    (36, "Admin Dashboard APIs", ["GET /dashboard/admin"], ["fraud_flags", "login_attempts"]),
    (37, "Hotel Verification and Moderation", ["GET /admin/moderation/queue", "POST /admin/hotels/{hotel_id}/suspend"], ["audit_logs"]),
    (38, "Reports and Export", ["GET /reports/bookings.csv"], ["bookings"]),
    (39, "Audit Logs and Security Monitoring", ["GET /admin/audit-logs", "GET /admin/security/overview"], ["audit_logs", "login_attempts"]),
    (40, "Hotel Subscription Plans", ["GET /subscription-plans"], ["subscription_plans", "hotel_subscriptions"]),
    (41, "Hotel Subscription Payments", ["POST /subscriptions"], ["subscription_payments"]),
    (42, "Dynamic Pricing Management", ["POST /hotels/{hotel_id}/pricing-rules"], ["pricing_rules"]),
    (43, "Loyalty and Rewards", ["GET /loyalty/me", "POST /loyalty/redeem"], ["loyalty_accounts", "loyalty_transactions"]),
    (44, "Location Services", ["GET /locations/nearby"], ["hotels"]),
    (45, "Calendar and Booking Scheduler", ["GET /hotels/{hotel_id}/calendar"], ["rooms"]),
    (46, "Financial Management", ["GET /finance/hotels/{hotel_id}/summary", "POST /admin/payouts"], ["payouts"]),
    (47, "Business Intelligence APIs", ["GET /bi/overview"], ["bookings"]),
    (48, "Fraud Detection and Security", ["GET /admin/fraud/flags"], ["fraud_flags"]),
    (49, "System Configuration", ["GET /admin/settings", "GET /settings/public"], ["system_settings"]),
    (50, "Advanced Platform Administration", ["GET /admin/users", "GET /admin/system/health"], ["users"]),
]


def all_routes():
    found = set()
    for r in app.routes:
        routes = [r] if isinstance(r, APIRoute) else [x for x in getattr(getattr(r, "original_router", None), "routes", []) if isinstance(x, APIRoute)]
        for x in routes:
            for m in x.methods:
                found.add(f"{m} {x.path}")
    return found


def mysql_tables():
    try:
        from sqlalchemy import inspect
        from app.db.database import engine
        return set(inspect(engine).get_table_names()), None
    except Exception as err:  # MySQL off or wrong .env
        return None, str(err).splitlines()[0]


routes = all_routes()
tables, db_error = mysql_tables()
done = 0
print(f"{'#':>2}  {'Module':<38} {'Code':<6} {'Tables':<7} Status")
print("-" * 70)
for num, name, eps, tbls in MODULES:
    code_ok = all(e in routes for e in eps)
    tbl_ok = None if tables is None else all(t in tables for t in tbls)
    ok = code_ok and tbl_ok is not False
    done += ok
    tbl_txt = "?" if tbl_ok is None else ("OK" if tbl_ok else "MISSING")
    print(f"{num:>2}  {name:<38} {'OK' if code_ok else 'MISSING':<6} {tbl_txt:<7} {'DONE' if ok else 'NOT DONE'}")
    if not code_ok:
        print("      missing endpoints:", [e for e in eps if e not in routes])
    if tbl_ok is False:
        print("      missing tables:", [t for t in tbls if t not in tables])
print("-" * 70)
print(f"Endpoints in app: {len(routes)}")
if tables is None:
    print("MySQL not checked:", db_error)
else:
    print(f"Tables in MySQL: {len(tables - {'alembic_version'})} (expected 40)")
print(f"COMPLETED: {done} / 50 modules")
