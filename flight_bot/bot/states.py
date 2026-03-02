from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    waiting_for_city = State()


class SubscribeStates(StatesGroup):
    waiting_for_city_input = State()
    waiting_for_country_input = State()
