"""38. Reports and export - CSV files that open in Excel."""

import csv
import io
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Booking, Hotel, Payout
from app.services import analytics_service


def _to_csv(header: list[str], rows: list[list]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()


def bookings_csv(db: Session, hotel_ids: list[int], start: date, end: date) -> str:
    bookings = list(db.scalars(
        select(Booking).where(Booking.hotel_id.in_(hotel_ids or [-1]), Booking.check_in >= start, Booking.check_in <= end)
        .order_by(Booking.check_in, Booking.id)
    ))
    rows = [[
        b.booking_code, b.hotel.name, b.room_type.name, b.room.room_number, b.customer.full_name,
        b.check_in, b.check_out, b.nights, b.adults, b.children, b.status,
        b.subtotal, b.discount_amount, b.tax_amount, b.total_amount, b.created_at,
    ] for b in bookings]
    header = ["booking_code", "hotel", "room_type", "room", "guest", "check_in", "check_out", "nights",
              "adults", "children", "status", "subtotal", "discount", "tax", "total", "booked_at"]
    return _to_csv(header, rows)


def revenue_csv(db: Session, hotel_ids: list[int], start: date, end: date, group_by: str) -> str:
    report = analytics_service.revenue(db, hotel_ids, start, end, group_by)
    rows = [[r["period"], r["bookings"], r["room_revenue"], r["tax"], r["total"]] for r in report["series"]]
    rows.append(["TOTAL", report["total_bookings"], report["total_room_revenue"], report["total_tax"], report["total_revenue"]])
    return _to_csv(["period", "bookings", "room_revenue", "tax", "total"], rows)


def payouts_csv(db: Session, hotel_ids: list[int]) -> str:
    payouts = list(db.scalars(
        select(Payout).where(Payout.hotel_id.in_(hotel_ids or [-1])).order_by(Payout.period_start)
    ))
    hotels = {h.id: h.name for h in db.scalars(select(Hotel).where(Hotel.id.in_(hotel_ids or [-1])))}
    rows = [[p.id, hotels.get(p.hotel_id), p.period_start, p.period_end, p.bookings_count, p.gross_amount,
             p.commission_amount, p.net_amount, p.status, p.reference or "", p.paid_at or ""] for p in payouts]
    header = ["payout_id", "hotel", "period_start", "period_end", "stays", "gross", "commission", "net",
              "status", "reference", "paid_at"]
    return _to_csv(header, rows)
