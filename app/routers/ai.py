from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_roles
from app.models import RoleName, User
from app.schemas.ai import AIAnswer, ChatHistoryItem, ChatRequest, RecommendedHotel, TravelRequest
from app.services import ai_service

router = APIRouter(prefix="/ai", tags=["AI"])


@router.get("/recommendations", response_model=list[RecommendedHotel])
def recommendations(
    city: str | None = None,
    limit: int = Query(5, ge=1, le=20),
    user: User = Depends(require_roles(RoleName.CUSTOMER)),
    db: Session = Depends(get_db),
):
    return ai_service.recommend(db, user, limit, city)


@router.post("/travel-assistant", response_model=AIAnswer)
def travel_assistant(data: TravelRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ai_service.travel_assistant(
        db, user, data.city, data.days, data.budget_per_night, data.interests, data.question
    )


@router.post("/support-chat", response_model=AIAnswer)
def support_chat(data: ChatRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ai_service.support_chat(db, user, data.message)


@router.get("/chat-history", response_model=list[ChatHistoryItem])
def chat_history(
    channel: Literal["TRAVEL", "SUPPORT"] | None = None,
    limit: int = Query(30, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ai_service.chat_history(db, user, channel, limit)
