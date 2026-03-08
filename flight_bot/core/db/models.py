from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db.base import Base


class Country(Base):
    __tablename__ = "countries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name_ru: Mapped[str] = mapped_column(String, nullable=False)
    name_en: Mapped[str] = mapped_column(String, nullable=False)
    region: Mapped[str | None] = mapped_column(String, nullable=True)

    cities: Mapped[list["City"]] = relationship(back_populates="country")


class City(Base):
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    iata: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name_ru: Mapped[str] = mapped_column(String, nullable=False)
    name_en: Mapped[str] = mapped_column(String, nullable=False)
    country_code: Mapped[str] = mapped_column(
        String, ForeignKey("countries.code"), nullable=False
    )

    country: Mapped["Country"] = relationship(back_populates="cities")
    airports: Mapped[list["Airport"]] = relationship(back_populates="city")


class Airport(Base):
    __tablename__ = "airports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    iata: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name_ru: Mapped[str] = mapped_column(String, nullable=False)
    name_en: Mapped[str] = mapped_column(String, nullable=False)
    city_iata: Mapped[str] = mapped_column(
        String, ForeignKey("cities.iata"), nullable=False
    )
    country_code: Mapped[str] = mapped_column(
        String, ForeignKey("countries.code"), nullable=False
    )

    city: Mapped["City"] = relationship(back_populates="airports")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    origin_iata: Mapped[str | None] = mapped_column(
        String, ForeignKey("cities.iata"), nullable=True
    )
    threshold_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    quiet_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quiet_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user")

    __table_args__ = (
        CheckConstraint(
            "threshold_pct BETWEEN 20 AND 50",
            name="ck_users_threshold_pct",
        ),
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    origin_iata: Mapped[str] = mapped_column(String, ForeignKey("cities.iata"), nullable=False)
    dest_type: Mapped[str] = mapped_column(String, nullable=False)
    dest_code: Mapped[str] = mapped_column(String, nullable=False)
    date_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    max_stops: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_duration: Mapped[int | None] = mapped_column(Integer, nullable=True)  # минуты
    target_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="subscriptions")

    __table_args__ = (
        UniqueConstraint("user_id", "origin_iata", "dest_type", "dest_code", name="uq_user_origin_dest"),
    )


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    route_key: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    ticket_link: Mapped[str] = mapped_column(String, nullable=False)
    found_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_price_history_route_found", "route_key", "found_at"),
    )


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_name: Mapped[str | None] = mapped_column(String, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    replied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscriptions.id"), nullable=False
    )
    route_key: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_price: Mapped[int] = mapped_column(Integer, nullable=False)
    discount_pct: Mapped[int] = mapped_column(Integer, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_notifications_sub_route_sent",
            "subscription_id",
            "route_key",
            "sent_at",
        ),
    )
