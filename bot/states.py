from aiogram.fsm.state import State, StatesGroup


class ProfileCreation(StatesGroup):
    name = State()
    age = State()
    gender = State()
    city = State()
    interests = State()
    preferences = State()
    bio = State()
    photo = State()


class ProfileEdit(StatesGroup):
    choosing_field = State()
    editing_value = State()
