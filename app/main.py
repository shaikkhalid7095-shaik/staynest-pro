from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_db
from app.routers import (
    admin, ai, amenities, analytics, auth, bookings, checkin, coupons, gallery, hotels, housekeeping, messages,
    notifications, payments, platform, pricing, reviews, rooms, search, services, staff, subscriptions, users, wishlist,
)

app = FastAPI(
    title=settings.app_name,
    description="Hotel, resort and room booking backend",
    version="1.0.0",
)

# day 1
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(hotels.router)
app.include_router(amenities.router)
app.include_router(rooms.router)

# day 2
app.include_router(search.router)
app.include_router(gallery.router)
app.include_router(bookings.router)
app.include_router(payments.router)
app.include_router(coupons.router)
app.include_router(reviews.router)
app.include_router(wishlist.router)

# day 3
app.include_router(ai.router)
app.include_router(notifications.router)
app.include_router(messages.router)
app.include_router(staff.router)
app.include_router(housekeeping.router)
app.include_router(checkin.router)
app.include_router(services.router)
app.include_router(subscriptions.router)
app.include_router(pricing.router)

# day 4
app.include_router(analytics.router)
app.include_router(admin.router)
app.include_router(platform.router)


@app.get("/", tags=["Health"])
def root():
    return {"message": "StayNest Pro API is running"}


@app.get("/health/db", tags=["Health"])
def check_db(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"database": "connected"}
