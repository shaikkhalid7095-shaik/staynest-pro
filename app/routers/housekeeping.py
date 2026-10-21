from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models import User
from app.schemas.staff import TaskCreate, TaskOut, TaskStatus, TaskUpdate
from app.services import housekeeping_service, staff_service

router = APIRouter(prefix="/hotels/{hotel_id}/housekeeping", tags=["Housekeeping"])

# every endpoint here checks get_operable_hotel: admin, the owner, or staff of this hotel


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(hotel_id: int, data: TaskCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    hotel = staff_service.get_operable_hotel(db, hotel_id, user)
    return housekeeping_service.create_task(db, hotel, data)


@router.get("", response_model=list[TaskOut])
def list_tasks(
    hotel_id: int,
    task_status: TaskStatus | None = None,
    room_id: int | None = None,
    mine: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    hotel = staff_service.get_operable_hotel(db, hotel_id, user)
    return housekeeping_service.list_tasks(db, hotel, task_status, room_id, user.id if mine else None)


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(
    hotel_id: int, task_id: int, data: TaskUpdate,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    hotel = staff_service.get_operable_hotel(db, hotel_id, user)
    task = housekeeping_service.get_task(db, hotel, task_id)
    return housekeeping_service.update_task(db, hotel, task, data, user)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(hotel_id: int, task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    hotel = staff_service.get_operable_hotel(db, hotel_id, user)
    housekeeping_service.delete_task(db, housekeeping_service.get_task(db, hotel, task_id))
