from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Hotel, HotelStaff, HousekeepingTask, Room, RoomStatus, User
from app.schemas.staff import TaskCreate, TaskUpdate
from app.utils.time import utcnow


def _check_assignee(db: Session, hotel: Hotel, user_id: int | None):
    if user_id is None:
        return
    staff = db.scalar(
        select(HotelStaff).where(
            HotelStaff.user_id == user_id, HotelStaff.hotel_id == hotel.id, HotelStaff.is_active.is_(True)
        )
    )
    if staff is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "assigned_to_id must be an active staff member of this hotel")


def create_task(db: Session, hotel: Hotel, data: TaskCreate, booking_id: int | None = None) -> HousekeepingTask:
    room = db.get(Room, data.room_id)
    if room is None or room.hotel_id != hotel.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Room not found in this hotel")
    _check_assignee(db, hotel, data.assigned_to_id)

    task = HousekeepingTask(**data.model_dump(), hotel_id=hotel.id, booking_id=booking_id)
    # a maintenance job takes the room off sale until it's done
    if data.task_type == "MAINTENANCE" and room.status != RoomStatus.OCCUPIED:
        room.status = RoomStatus.MAINTENANCE.value
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def list_tasks(
    db: Session, hotel: Hotel, task_status: str | None, room_id: int | None, assigned_to: int | None
) -> list[HousekeepingTask]:
    query = select(HousekeepingTask).where(HousekeepingTask.hotel_id == hotel.id)
    if task_status:
        query = query.where(HousekeepingTask.status == task_status)
    if room_id:
        query = query.where(HousekeepingTask.room_id == room_id)
    if assigned_to:
        query = query.where(HousekeepingTask.assigned_to_id == assigned_to)
    # HIGH first, then oldest first
    priority_order = {"HIGH": 0, "NORMAL": 1, "LOW": 2}
    tasks = list(db.scalars(query.order_by(HousekeepingTask.id)))
    return sorted(tasks, key=lambda t: priority_order.get(t.priority, 1))


def get_task(db: Session, hotel: Hotel, task_id: int) -> HousekeepingTask:
    task = db.get(HousekeepingTask, task_id)
    if task is None or task.hotel_id != hotel.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return task


def update_task(db: Session, hotel: Hotel, task: HousekeepingTask, data: TaskUpdate, user: User) -> HousekeepingTask:
    changes = data.model_dump(exclude_unset=True)
    if "assigned_to_id" in changes:
        _check_assignee(db, hotel, changes["assigned_to_id"])

    new_status = changes.get("status")
    if task.status == "DONE" and new_status and new_status != "DONE":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A finished task can't be reopened. Create a new one")

    for field, value in changes.items():
        setattr(task, field, value)

    if new_status == "IN_PROGRESS" and task.assigned_to_id is None:
        task.assigned_to_id = user.id  # whoever starts it owns it
    if new_status == "DONE":
        task.completed_at = utcnow()
        if task.task_type == "MAINTENANCE" and task.room.status == RoomStatus.MAINTENANCE:
            task.room.status = RoomStatus.AVAILABLE.value

    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, task: HousekeepingTask):
    if task.status == "IN_PROGRESS":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Someone is working on this task")
    db.delete(task)
    db.commit()


def cleaning_after_checkout(hotel_id: int, room_id: int, booking_id: int) -> HousekeepingTask:
    return HousekeepingTask(
        hotel_id=hotel_id, room_id=room_id, booking_id=booking_id,
        task_type="CLEANING", priority="HIGH", due_date=date.today(),
        notes="Guest checked out",
    )
