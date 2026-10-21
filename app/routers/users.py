from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_roles
from app.models import CustomerProfile, RoleName, User
from app.schemas.user import CustomerProfileOut, CustomerProfileUpdate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["Users & Profiles"])


@router.put("/me", response_model=UserOut)
def update_me(data: UserUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    changes = data.model_dump(exclude_unset=True)

    if changes.get("phone"):
        taken = db.scalar(select(User).where(User.phone == changes["phone"], User.id != user.id))
        if taken:
            raise HTTPException(status.HTTP_409_CONFLICT, "Phone number is already registered")

    for field, value in changes.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return UserOut.from_user(user)


def _get_profile(db: Session, user: User) -> CustomerProfile:
    profile = user.customer_profile
    if profile is None:
        profile = CustomerProfile(user_id=user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


@router.get("/me/profile", response_model=CustomerProfileOut)
def get_my_profile(
    user: User = Depends(require_roles(RoleName.CUSTOMER)), db: Session = Depends(get_db)
):
    return _get_profile(db, user)


@router.put("/me/profile", response_model=CustomerProfileOut)
def update_my_profile(
    data: CustomerProfileUpdate,
    user: User = Depends(require_roles(RoleName.CUSTOMER)),
    db: Session = Depends(get_db),
):
    profile = _get_profile(db, user)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return profile
