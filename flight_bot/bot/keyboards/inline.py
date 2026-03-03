from datetime import date
from calendar import monthrange

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

_MONTHS_NOM = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
}


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✈️ Подписаться", callback_data="subscribe")],
            [InlineKeyboardButton(text="📋 Мои подписки", callback_data="my_subs")],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
        ]
    )


def subscribe_type() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🌏 Регион", callback_data="sub_region"),
                InlineKeyboardButton(text="🏳 Страна", callback_data="sub_country"),
                InlineKeyboardButton(text="🏙 Город", callback_data="sub_city"),
            ]
        ]
    )


def region_select() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌴 ЮВА", callback_data="region:ЮВА")],
            [InlineKeyboardButton(text="🏰 Европа", callback_data="region:Европа")],
            [
                InlineKeyboardButton(
                    text="🕌 ОАЭ и Ближний Восток",
                    callback_data="region:ОАЭ и Ближний Восток",
                )
            ],
        ]
    )


def city_select(cities: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    """cities: список (iata, name_ru)."""
    buttons = [
        [InlineKeyboardButton(text=f"{name} ({iata})", callback_data=f"city:{iata}")]
        for iata, name in cities
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def country_select(countries: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    """countries: список (code, name_ru)."""
    buttons = [
        [InlineKeyboardButton(text=name, callback_data=f"country:{code}")]
        for code, name in countries
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def subscription_list(
    subs: list, dest_labels: dict[int, str]
) -> InlineKeyboardMarkup:
    """Список подписок с кнопкой удаления."""
    buttons = []
    for i, sub in enumerate(subs, 1):
        label = dest_labels.get(sub.id, sub.dest_code)
        buttons.append(
            [InlineKeyboardButton(
                text=f"{i}. {label}",
                callback_data=f"sub_info:{sub.id}",
            )]
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    text="✏️ Изменить",
                    callback_data=f"edit_sub:{sub.id}",
                ),
                InlineKeyboardButton(
                    text="❌ Удалить",
                    callback_data=f"unsub:{sub.id}",
                ),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def stops_select() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✈️ Только прямые", callback_data="stops:0")],
            [InlineKeyboardButton(text="1️⃣ Макс. 1 пересадка", callback_data="stops:1")],
            [InlineKeyboardButton(text="2️⃣ Макс. 2 пересадки", callback_data="stops:2")],
        ]
    )


def date_type_select() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📅 Конкретная дата", callback_data="date_type:specific"),
                InlineKeyboardButton(text="📆 Диапазон дат", callback_data="date_type:range"),
            ],
            [
                InlineKeyboardButton(text="🗓 Месяц", callback_data="date_type:month"),
                InlineKeyboardButton(text="⏩ Любая дата", callback_data="date_type:any"),
            ],
        ]
    )


def month_select() -> InlineKeyboardMarkup:
    today = date.today()
    buttons = []
    row = []
    for i in range(12):
        total_month = today.month - 1 + i
        m = total_month % 12 + 1
        y = today.year + total_month // 12
        label = f"{_MONTHS_NOM[m]} {y}"
        row.append(InlineKeyboardButton(text=label, callback_data=f"date_month:{y}-{m:02d}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def add_first_subscription() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Добавить подписку", callback_data="subscribe"
                )
            ]
        ]
    )
