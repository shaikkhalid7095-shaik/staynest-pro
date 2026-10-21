"""AI features: hotel recommendations, travel assistant and support chatbot.

Recommendations are a scoring formula over our own data - no outside service.
The assistant and chatbot use Claude when ANTHROPIC_API_KEY is set in .env.
Without a key (or if the call fails) they fall back to simple rule-based
answers, so the APIs always work during testing.
"""

from collections import Counter
from datetime import date
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Booking, BookingStatus, ChatMessage, Hotel, HotelStatus, User, WishlistItem
from app.services import pricing_service, review_service

CLAUDE_URL = "https://api.anthropic.com/v1/messages"
HISTORY_TURNS = 6  # how many earlier messages we send back to Claude for context


# ---------- 21. recommendations ----------

def _starting_price(hotel: Hotel) -> Decimal | None:
    prices = [pricing_service.nightly_rate(t, date.today()) for t in hotel.room_types if t.is_active]
    return min(prices) if prices else None


def recommend(db: Session, user: User, limit: int = 5, city: str | None = None) -> list[dict]:
    query = select(Hotel).where(Hotel.status == HotelStatus.APPROVED.value, Hotel.is_active.is_(True))
    if city:
        query = query.where(Hotel.city.ilike(f"%{city.strip()}%"))
    hotels = list(db.scalars(query))
    if not hotels:
        return []

    past = list(db.scalars(
        select(Booking).where(
            Booking.customer_id == user.id,
            Booking.status.in_([BookingStatus.CONFIRMED.value, BookingStatus.CHECKED_IN.value,
                                BookingStatus.CHECKED_OUT.value]),
        )
    ))
    wishlist_ids = set(db.scalars(select(WishlistItem.hotel_id).where(WishlistItem.customer_id == user.id)))
    liked_cities = Counter(b.hotel.city.lower() for b in past)
    for item_hotel in hotels:
        if item_hotel.id in wishlist_ids:
            liked_cities[item_hotel.city.lower()] += 1
    stayed_ids = {b.hotel_id for b in past}
    usual_rate = (sum(b.room_rate for b in past) / len(past)) if past else None
    ratings = review_service.rating_stats(db, [h.id for h in hotels])

    results = []
    for hotel in hotels:
        price = _starting_price(hotel)
        if price is None:
            continue
        score, reasons = 0.0, []

        avg, count = ratings.get(hotel.id, (None, 0))
        if avg:
            score += avg  # up to 5 points
            reasons.append(f"Rated {avg} by {count} guest(s)")
        if hotel.city.lower() in liked_cities:
            score += 2 + liked_cities[hotel.city.lower()] * 0.5
            reasons.append(f"You like {hotel.city}")
        if hotel.id in wishlist_ids:
            score += 2
            reasons.append("In your wishlist")
        if hotel.id in stayed_ids:
            score += 1
            reasons.append("You stayed here before")
        if usual_rate:
            # closer to what the guest usually pays = better fit
            gap = abs(float(price) - float(usual_rate)) / float(usual_rate)
            fit = max(0.0, 2 - gap * 2)
            score += fit
            if fit > 1:
                reasons.append("Matches your usual budget")
        if hotel.star_rating:
            score += hotel.star_rating * 0.2

        if not reasons:
            reasons.append("Popular choice")
        results.append({
            "hotel_id": hotel.id, "name": hotel.name, "city": hotel.city,
            "star_rating": hotel.star_rating, "starting_price": price,
            "avg_rating": avg, "score": round(score, 2), "reasons": reasons,
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]


# ---------- Claude helper ----------

def ask_claude(system: str, messages: list[dict]) -> str | None:
    """Returns Claude's reply, or None if there's no key or the call fails."""
    if not settings.anthropic_api_key:
        return None
    try:
        resp = httpx.post(
            CLAUDE_URL,
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={"model": settings.ai_model, "max_tokens": 800, "system": system, "messages": messages},
            timeout=30,
        )
        resp.raise_for_status()
        parts = resp.json().get("content", [])
        text = "".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()
        return text or None
    except (httpx.HTTPError, ValueError):
        return None


def _history(db: Session, user: User, channel: str) -> list[dict]:
    rows = list(db.scalars(
        select(ChatMessage)
        .where(ChatMessage.user_id == user.id, ChatMessage.channel == channel)
        .order_by(ChatMessage.id.desc())
        .limit(HISTORY_TURNS)
    ))
    rows.reverse()
    messages = [{"role": r.role, "content": r.content} for r in rows]
    # Claude wants the conversation to start with the user
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    return messages


def _save(db: Session, user: User, channel: str, question: str, answer: str):
    db.add(ChatMessage(user_id=user.id, channel=channel, role="user", content=question))
    db.add(ChatMessage(user_id=user.id, channel=channel, role="assistant", content=answer))
    db.commit()


# ---------- 22. travel assistant ----------

def _rule_based_plan(city: str, days: int, hotels: list[dict], interests: str | None) -> str:
    lines = [f"Here is a simple {days}-day plan for {city}:"]
    hotel_name = hotels[0]["name"] if hotels else "your hotel"
    for day in range(1, days + 1):
        if day == 1:
            lines.append(f"Day 1: Check in at {hotel_name}, rest, and explore the area around it in the evening.")
        elif day == days:
            lines.append(f"Day {day}: Pack, check out before noon, and pick up local snacks or souvenirs.")
        else:
            focus = interests or "the main sights and local food"
            lines.append(f"Day {day}: Spend the day on {focus}. Start early to avoid crowds and heat.")
    if hotels:
        names = ", ".join(f"{h['name']} (from Rs {h['starting_price']}/night)" for h in hotels)
        lines.append(f"Hotels we have in {city}: {names}.")
    else:
        lines.append(f"We don't have approved hotels in {city} yet.")
    lines.append("Tip: book at least 48 hours ahead so you get a full refund if plans change.")
    return "\n".join(lines)


def travel_assistant(db: Session, user: User, city: str, days: int, budget, interests, question) -> dict:
    hotels = recommend(db, user, limit=10, city=city)
    if budget:
        hotels = [h for h in hotels if h["starting_price"] <= budget] or hotels
    hotels = hotels[:3]

    request_text = f"Plan {days} days in {city}."
    if budget:
        request_text += f" Budget about Rs {budget} per night."
    if interests:
        request_text += f" Interests: {interests}."
    if question:
        request_text += f" {question}"

    hotel_lines = "\n".join(
        f"- {h['name']}, {h['star_rating'] or '?'} stars, from Rs {h['starting_price']}/night, rating {h['avg_rating']}"
        for h in hotels
    ) or "- (no hotels listed in this city yet)"
    system = (
        "You are the StayNest travel assistant for travellers in India. Give a short, practical "
        "day-by-day plan. Only recommend hotels from this list, which are on our platform:\n"
        f"{hotel_lines}\nKeep the answer under 250 words."
    )
    messages = _history(db, user, "TRAVEL") + [{"role": "user", "content": request_text}]

    answer = ask_claude(system, messages)
    source = "claude"
    if answer is None:
        answer = _rule_based_plan(city, days, hotels, interests)
        source = "rules"

    _save(db, user, "TRAVEL", request_text, answer)
    return {"answer": answer, "source": source, "hotels": hotels}


# ---------- 23. support chatbot ----------

POLICY = (
    "Cancellation: 48+ hours before check-in = 100% refund, 24-48 hours = 50%, under 24 hours = no refund. "
    "If the hotel cancels, the guest always gets 100%. Refunds go back to the card in 5-7 working days. "
    "Unpaid bookings hold the room for 15 minutes. Standard check-in is 2 PM and check-out 11 AM. "
    "GST: 12% for rooms up to Rs 7,500 per night, 18% above that. Room service works only after check-in."
)


def _latest_booking_text(db: Session, user: User) -> str:
    booking = db.scalar(select(Booking).where(Booking.customer_id == user.id).order_by(Booking.id.desc()).limit(1))
    if booking is None:
        return "You don't have any bookings yet."
    return (
        f"Your latest booking {booking.booking_code} at {booking.hotel.name} "
        f"({booking.check_in} to {booking.check_out}) is {booking.status.replace('_', ' ').lower()}, "
        f"total Rs {booking.total_amount}."
    )


def _rule_based_support(db: Session, user: User, text: str) -> str:
    t = text.lower()
    if any(w in t for w in ("refund", "cancel")):
        return ("Our cancellation policy: 48+ hours before check-in you get a full refund, 24-48 hours 50%, "
                "and under 24 hours no refund. Use GET /bookings/{id}/refund-quote to see your exact amount "
                "before cancelling. Refunds reach your card in 5-7 working days.")
    if any(w in t for w in ("my booking", "status", "where is", "confirm")):
        return _latest_booking_text(db, user)
    if any(w in t for w in ("check-in", "check in", "checkin", "check-out", "check out", "checkout", "time")):
        return "Standard check-in is from 2 PM and check-out is by 11 AM. Each hotel's exact times are on its details page."
    if any(w in t for w in ("pay", "card", "payment", "charged")):
        return ("We take card payments through Stripe. Your room is held for 15 minutes while you pay. "
                "If money was taken but the booking isn't confirmed, it's refunded automatically.")
    if any(w in t for w in ("coupon", "discount", "offer", "promo")):
        return "Enter a coupon code when booking. You can check one first with POST /coupons/validate."
    if any(w in t for w in ("gst", "tax")):
        return "GST is 12% for rooms up to Rs 7,500 per night and 18% above that. It's shown on your invoice."
    if any(w in t for w in ("room service", "food", "breakfast", "spa")):
        return "You can order hotel services from your booking. Room service is available once you've checked in."
    if any(w in t for w in ("human", "agent", "person", "complain")):
        return "I've noted that you'd like to talk to a person. You can also message the hotel directly from your booking."
    return ("I can help with bookings, cancellations and refunds, payments, check-in times, coupons and room service. "
            "What would you like to know?")


def support_chat(db: Session, user: User, text: str) -> dict:
    system = (
        "You are the StayNest customer support assistant. Answer briefly and politely using only these "
        f"facts:\n{POLICY}\nCustomer's account: {_latest_booking_text(db, user)}\n"
        "If you don't know something, say so and suggest messaging the hotel from the booking."
    )
    messages = _history(db, user, "SUPPORT") + [{"role": "user", "content": text}]

    answer = ask_claude(system, messages)
    source = "claude"
    if answer is None:
        answer = _rule_based_support(db, user, text)
        source = "rules"

    _save(db, user, "SUPPORT", text, answer)
    return {"answer": answer, "source": source, "hotels": []}


def chat_history(db: Session, user: User, channel: str | None, limit: int) -> list[ChatMessage]:
    query = select(ChatMessage).where(ChatMessage.user_id == user.id)
    if channel:
        query = query.where(ChatMessage.channel == channel)
    rows = list(db.scalars(query.order_by(ChatMessage.id.desc()).limit(limit)))
    rows.reverse()
    return rows
