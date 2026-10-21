from sqlalchemy import select

from app.core.security import hash_password
from app.db.database import SessionLocal
from app.models import Amenity, Permission, Role, RoleName, SubscriptionPlan, User

ROLE_DESCRIPTIONS = {
    RoleName.CUSTOMER: "Books hotels and rooms",
    RoleName.HOTEL_OWNER: "Owns and manages hotels",
    RoleName.HOTEL_STAFF: "Works at a hotel",
    RoleName.ADMIN: "Platform administrator",
}

# starting set - we add more as modules get built
PERMISSIONS = {
    "hotel:create": "Register a new hotel",
    "hotel:verify": "Approve or reject hotels",
    "room:manage": "Add and edit rooms",
    "booking:create": "Book a room",
    "booking:view_all": "See every booking on the platform",
    "staff:manage": "Add and manage hotel staff",
    "checkin:manage": "Check guests in and out",
    "user:manage": "Activate or block users",
}

ROLE_PERMISSIONS = {
    RoleName.CUSTOMER: ["booking:create"],
    RoleName.HOTEL_OWNER: ["hotel:create", "room:manage", "staff:manage", "checkin:manage"],
    RoleName.HOTEL_STAFF: ["checkin:manage"],
    RoleName.ADMIN: list(PERMISSIONS.keys()),
}

AMENITIES = [
    ("Free WiFi", "GENERAL"), ("Parking", "GENERAL"), ("Swimming Pool", "GENERAL"),
    ("Gym", "GENERAL"), ("Restaurant", "FOOD"), ("Room Service", "FOOD"),
    ("Air Conditioning", "ROOM"), ("TV", "ROOM"), ("Spa", "WELLNESS"),
]

# day 3: what hotel owners can subscribe to (price in rupees per month)
PLANS = [
    ("BASIC", "For a single small property", 0, 1, "1 hotel,Bookings,Reviews"),
    ("STANDARD", "For growing hotel owners", 999, 3, "3 hotels,Staff accounts,Dynamic pricing,Room service"),
    ("PREMIUM", "For hotel chains", 2499, 10, "10 hotels,Everything in Standard,Priority support"),
]

# change this password after your first login
ADMIN_EMAIL = "admin@staynest.com"
ADMIN_PASSWORD = "Admin@12345"


def seed():
    db = SessionLocal()
    try:
        perms = {}
        for code, desc in PERMISSIONS.items():
            perm = db.scalar(select(Permission).where(Permission.code == code))
            if perm is None:
                perm = Permission(code=code, description=desc)
                db.add(perm)
            perms[code] = perm

        roles = {}
        for role_name, codes in ROLE_PERMISSIONS.items():
            role = db.scalar(select(Role).where(Role.name == role_name.value))
            if role is None:
                role = Role(name=role_name.value, description=ROLE_DESCRIPTIONS[role_name])
                db.add(role)
            role.permissions = [perms[c] for c in codes]
            roles[role_name] = role

        for name, category in AMENITIES:
            if db.scalar(select(Amenity).where(Amenity.name == name)) is None:
                db.add(Amenity(name=name, category=category))

        for name, desc, price, max_hotels, features in PLANS:
            if db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.name == name)) is None:
                db.add(SubscriptionPlan(
                    name=name, description=desc, price_monthly=price, max_hotels=max_hotels, features=features,
                ))

        if db.scalar(select(User).where(User.email == ADMIN_EMAIL)) is None:
            db.add(User(
                email=ADMIN_EMAIL,
                password_hash=hash_password(ADMIN_PASSWORD),
                full_name="Platform Admin",
                role=roles[RoleName.ADMIN],
                is_email_verified=True,
            ))

        db.commit()
        print("Seed done: roles, permissions, amenities, plans and admin user")
        print(f"Admin login -> {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
