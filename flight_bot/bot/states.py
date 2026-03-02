from aiogram.fsm.state import State, StatesGroup


class SubscribeStates(StatesGroup):
    waiting_for_origin_city = State()
    waiting_for_city_input = State()
    waiting_for_country_input = State()
    waiting_for_date_input = State()
    waiting_for_target_price = State()
