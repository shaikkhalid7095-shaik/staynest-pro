from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Booking, BookingStatus, Review, RoleName, User
from app.schemas.review import ReviewCreate
from app.utils.time import utcnow


def rating_stats(db: Session, hotel_ids: list[int]) -> dict[int, tuple[float, int]]:
    """{hotel_id: (average rating, number of reviews)} for visible reviews only."""
    if not hotel_ids:
        return {}
    rows = db.execute(
        select(Review.hotel_id, func.avg(Review.rating), func.count(Review.id))
        .where(Review.hotel_id.in_(hotel_ids), Review.is_visible.is_(True))
        .group_by(Review.hotel_id)
    )
    return {hotel_id: (round(float(avg), 1), count) for hotel_id, avg, count in rows}


def create_review(db: Session, user: User, data: ReviewCreate) -> Review:
    booking = db.get(Booking, data.booking_id)
    if booking is None or booking.customer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")

    stayed = booking.status == BookingStatus.CHECKED_OUT or (
        booking.status == BookingStatus.CONFIRMED and booking.check_out <= date.today()
    )
    if not stayed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can review only after your stay")

    if db.scalar(select(Review).where(Review.booking_id == booking.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "You already reviewed this booking")

    review = Review(**data.model_dump(), hotel_id=booking.hotel_id, customer_id=user.id)
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


def get_review(db: Session, review_id: int) -> Review:
    review = db.get(Review, review_id)
    if review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found")
    return review


def reply(db: Session, review: Review, text: str) -> Review:
    review.owner_reply = text
    review.replied_at = utcnow()
    db.commit()
    db.refresh(review)
    return review


def delete_review(db: Session, review: Review, user: User):
    if review.customer_id != user.id and user.role.name != RoleName.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can delete only your own review")
    db.delete(review)
    db.commit()