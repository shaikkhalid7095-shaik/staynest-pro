from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_roles
from app.models import Review, RoleName, User
from app.schemas.review import HotelReviews, ReviewCreate, ReviewOut, ReviewReply, ReviewVisibility
from app.services import hotel_service, review_service

router = APIRouter(tags=["Reviews & Ratings"])


@router.post("/reviews", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
def create_review(
    data: ReviewCreate,
    user: User = Depends(require_roles(RoleName.CUSTOMER)),
    db: Session = Depends(get_db),
):
    return review_service.create_review(db, user, data)


@router.get("/hotels/{hotel_id}/reviews", response_model=HotelReviews)
def hotel_reviews(hotel_id: int, db: Session = Depends(get_db)):
    hotel = hotel_service.get_public_hotel(db, hotel_id)
    reviews = list(db.scalars(
        select(Review)
        .where(Review.hotel_id == hotel.id, Review.is_visible.is_(True))
        .order_by(Review.created_at.desc())
    ))
    avg, count = review_service.rating_stats(db, [hotel.id]).get(hotel.id, (None, 0))
    return HotelReviews(hotel_id=hotel.id, avg_rating=avg, review_count=count, reviews=reviews)


@router.post("/reviews/{review_id}/reply", response_model=ReviewOut)
def reply_to_review(
    review_id: int,
    data: ReviewReply,
    user: User = Depends(require_roles(RoleName.HOTEL_OWNER, RoleName.ADMIN)),
    db: Session = Depends(get_db),
):
    review = review_service.get_review(db, review_id)
    hotel_service.get_manageable_hotel(db, review.hotel_id, user)  # must be this hotel's owner
    return review_service.reply(db, review, data.reply)


@router.patch("/reviews/{review_id}/visibility", response_model=ReviewOut)
def set_visibility(
    review_id: int,
    data: ReviewVisibility,
    _: User = Depends(require_roles(RoleName.ADMIN)),
    db: Session = Depends(get_db),
):
    review = review_service.get_review(db, review_id)
    review.is_visible = data.is_visible
    db.commit()
    db.refresh(review)
    return review


@router.delete("/reviews/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(review_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    review = review_service.get_review(db, review_id)
    review_service.delete_review(db, review, user)