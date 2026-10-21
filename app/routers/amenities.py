from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.models import Amenity, RoleName, User
from app.schemas.hotel import AmenityCreate, AmenityOut

router = APIRouter(prefix="/amenities", tags=["Amenities"])


@router.get("", response_model=list[AmenityOut])
def list_amenities(db: Session = Depends(get_db)):
    return list(db.scalars(select(Amenity).order_by(Amenity.category, Amenity.name)))


@router.post("", response_model=AmenityOut, status_code=status.HTTP_201_CREATED)
def create_amenity(
    data: AmenityCreate,
    _: User = Depends(require_roles(RoleName.ADMIN)),
    db: Session = Depends(get_db),
):
    if db.scalar(select(Amenity).where(Amenity.name == data.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Amenity already exists")
    amenity = Amenity(**data.model_dump())
    db.add(amenity)
    db.commit()
    db.refresh(amenity)
    return amenity


@router.delete("/{amenity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_amenity(
    amenity_id: int,
    _: User = Depends(require_roles(RoleName.ADMIN)),
    db: Session = Depends(get_db),
):
    amenity = db.get(Amenity, amenity_id)
    if amenity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Amenity not found")
    db.delete(amenity)
    db.commit()
