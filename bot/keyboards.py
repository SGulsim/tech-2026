from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
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


def gender_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Мужской"), KeyboardButton(text="Женский")],
            [KeyboardButton(text="Другой")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def preferences_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Ищу девушку"), KeyboardButton(text="Ищу парня")],
            [KeyboardButton(text="Не важно")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def skip_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Пропустить")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def browse_keyboard(profile_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❤️ Лайк", callback_data=f"like:{profile_id}"),
                InlineKeyboardButton(text="👎 Пропустить", callback_data=f"skip:{profile_id}"),
            ],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="stop_browse")],
        ]
    )


def edit_profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Имя", callback_data="edit:name"),
                InlineKeyboardButton(text="🎂 Возраст", callback_data="edit:age"),
            ],
            [
                InlineKeyboardButton(text="🏙 Город", callback_data="edit:city"),
                InlineKeyboardButton(text="📖 О себе", callback_data="edit:bio"),
            ],
            [
                InlineKeyboardButton(text="🎯 Интересы", callback_data="edit:interests"),
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="my_profile")],
        ]
    )
