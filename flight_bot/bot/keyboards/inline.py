from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


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
            [InlineKeyboardButton(text="🌏 ЮВА", callback_data="region:ЮВА")],
            [InlineKeyboardButton(text="🌍 Европа", callback_data="region:Европа")],
            [
                InlineKeyboardButton(
                    text="🏜 ОАЭ и Ближний Восток",
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
    type_emoji = {"region": "🌏", "country": "🏳", "city": "🏙"}
    buttons = []
    for i, sub in enumerate(subs, 1):
        emoji = type_emoji.get(sub.dest_type, "")
        label = dest_labels.get(sub.id, sub.dest_code)
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{i}. {emoji} {label}",
                    callback_data=f"sub_info:{sub.id}",
                ),
                InlineKeyboardButton(
                    text="❌", callback_data=f"unsub:{sub.id}"
                ),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def threshold_select(current: int) -> InlineKeyboardMarkup:
    values = [20, 30, 40, 50]
    buttons = []
    for v in values:
        label = f"{'✅ ' if v == current else ''}{v}%"
        buttons.append(
            InlineKeyboardButton(text=label, callback_data=f"threshold:{v}")
        )
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


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
