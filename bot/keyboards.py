from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Моя анкета"), KeyboardButton(text="❤️ Смотреть анкеты")],
            [KeyboardButton(text="👥 Пригласить друга"), KeyboardButton(text="⚙️ Настройки")],
        ],
        resize_keyboard=True,
    )


def welcome_keyboard(is_new: bool) -> InlineKeyboardMarkup:
    if is_new:
        buttons = [
            [InlineKeyboardButton(text="✏️ Заполнить анкету", callback_data="create_profile")],
            [InlineKeyboardButton(text="ℹ️ Как это работает?", callback_data="how_it_works")],
        ]
    else:
        buttons = [
            [InlineKeyboardButton(text="👤 Моя анкета", callback_data="my_profile")],
            [InlineKeyboardButton(text="❤️ Смотреть анкеты", callback_data="browse_profiles")],
        ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def profile_actions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_profile")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")],
        ]
    )
