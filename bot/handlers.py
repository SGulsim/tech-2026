import structlog
from aiogram import Bot, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from api_client import backend_client
from keyboards import (
    browse_keyboard,
    edit_profile_keyboard,
    gender_keyboard,
    main_menu_keyboard,
    preferences_keyboard,
    profile_actions_keyboard,
    remove_keyboard,
    skip_keyboard,
    welcome_keyboard,
)
from mq_client import publish_action
from states import ProfileCreation, ProfileEdit

router = Router()
logger = structlog.get_logger(__name__)

_GENDER_MAP = {
    "Мужской": "male",
    "Женский": "female",
    "Другой": "other",
}
_PREFS_MAP = {
    "Ищу девушку": "female",
    "Ищу парня": "male",
    "Не важно": "any",
}


# ─────────────────────────────────────────────
# /start
# ─────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()

    user = message.from_user
    referrer_telegram_id: int | None = None

    args = message.text.split(maxsplit=1)
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_telegram_id = int(args[1].replace("ref_", ""))
        except ValueError:
            pass

    try:
        data = await backend_client.register_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            referrer_telegram_id=referrer_telegram_id,
        )
        is_new: bool = data.get("is_new", False)
        logger.info("user_start", telegram_id=user.id, is_new=is_new)

        if is_new:
            text = (
                f"👋 Привет, {user.first_name or 'незнакомец'}!\n\n"
                "Добро пожаловать в Dating Bot — место, где находят свою половинку.\n\n"
                "Давай начнём с заполнения анкеты — это займёт всего пару минут 🙂"
            )
        else:
            text = f"С возвращением, {user.first_name or 'друг'}! 👋\n\nРад снова тебя видеть."

        await message.answer(text, reply_markup=welcome_keyboard(is_new))

        if not is_new:
            await message.answer("Используй меню ниже:", reply_markup=main_menu_keyboard())

    except Exception as exc:
        logger.error("start_error", error=str(exc))
        await message.answer("😔 Ошибка подключения к серверу. Попробуй /start ещё раз.")


# ─────────────────────────────────────────────
# /help
# ─────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    text = (
        "📖 <b>Команды бота:</b>\n\n"
        "/start — начать / перезапустить бота\n"
        "/profile — посмотреть или создать анкету\n"
        "/browse — смотреть анкеты других\n"
        "/ref — получить реферальную ссылку\n"
        "/help — эта справка"
    )
    await message.answer(text, parse_mode="HTML")


# ─────────────────────────────────────────────
# /ref
# ─────────────────────────────────────────────

@router.message(Command("ref"))
async def cmd_ref(message: Message) -> None:
    bot_info = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{message.from_user.id}"
    await message.answer(
        f"👥 <b>Твоя реферальная ссылка:</b>\n\n<code>{ref_link}</code>\n\n"
        "Поделись ею с друзьями — они получат приоритет в ранжировании!",
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────
# /profile — просмотр или создание анкеты
# ─────────────────────────────────────────────

@router.message(Command("profile"))
@router.message(lambda m: m.text == "👤 Моя анкета")
async def cmd_profile(message: Message, state: FSMContext) -> None:
    try:
        profile = await backend_client.get_profile(message.from_user.id)
    except Exception as exc:
        logger.error("get_profile_error", error=str(exc))
        await message.answer("😔 Ошибка при загрузке анкеты.")
        return

    if not profile:
        await message.answer(
            "У тебя ещё нет анкеты. Давай создадим!\n\n"
            "Как тебя зовут?",
            reply_markup=remove_keyboard(),
        )
        await state.set_state(ProfileCreation.name)
    else:
        await _show_own_profile(message, profile)


async def _show_own_profile(message: Message, profile: dict) -> None:
    gender_display = {"male": "Мужской", "female": "Женский", "other": "Другой"}.get(
        profile.get("gender", ""), profile.get("gender", "—")
    )
    text = (
        f"👤 <b>Твоя анкета</b>\n\n"
        f"<b>Имя:</b> {profile.get('name', '—')}\n"
        f"<b>Возраст:</b> {profile.get('age', '—')}\n"
        f"<b>Пол:</b> {gender_display}\n"
        f"<b>Город:</b> {profile.get('city', '—')}\n"
        f"<b>Интересы:</b> {profile.get('interests', '—')}\n"
        f"<b>О себе:</b> {profile.get('bio', '—')}\n\n"
        f"📊 Заполненность: {profile.get('completeness_score', 0):.0f}/100\n"
        f"⭐ Рейтинг: {profile.get('rating_score', 0) or 0:.1f}"
    )
    photos = profile.get("photos", [])
    if photos:
        await message.answer_photo(photo=photos[0], caption=text, parse_mode="HTML",
                                   reply_markup=profile_actions_keyboard())
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=profile_actions_keyboard())


# ─────────────────────────────────────────────
# FSM — создание анкеты
# ─────────────────────────────────────────────

@router.message(ProfileCreation.name)
async def fsm_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if len(name) < 2 or len(name) > 50:
        await message.answer("Имя должно быть от 2 до 50 символов. Попробуй ещё раз:")
        return
    await state.update_data(name=name)
    await message.answer("Сколько тебе лет?")
    await state.set_state(ProfileCreation.age)


@router.message(ProfileCreation.age)
async def fsm_age(message: Message, state: FSMContext) -> None:
    try:
        age = int(message.text.strip())
        if not (16 <= age <= 100):
            raise ValueError
    except ValueError:
        await message.answer("Введи корректный возраст (16–100):")
        return
    await state.update_data(age=age)
    await message.answer("Укажи свой пол:", reply_markup=gender_keyboard())
    await state.set_state(ProfileCreation.gender)


@router.message(ProfileCreation.gender)
async def fsm_gender(message: Message, state: FSMContext) -> None:
    gender = _GENDER_MAP.get(message.text.strip())
    if not gender:
        await message.answer("Пожалуйста, выбери пол из предложенных вариантов:", reply_markup=gender_keyboard())
        return
    await state.update_data(gender=gender)
    await message.answer("В каком городе ты живёшь?", reply_markup=remove_keyboard())
    await state.set_state(ProfileCreation.city)


@router.message(ProfileCreation.city)
async def fsm_city(message: Message, state: FSMContext) -> None:
    city = message.text.strip()
    if len(city) < 2:
        await message.answer("Введи название города:")
        return
    await state.update_data(city=city)
    await message.answer(
        "Расскажи о своих интересах (например: музыка, путешествия, спорт).\n"
        "Или нажми «Пропустить»:",
        reply_markup=skip_keyboard(),
    )
    await state.set_state(ProfileCreation.interests)


@router.message(ProfileCreation.interests)
async def fsm_interests(message: Message, state: FSMContext) -> None:
    interests = None if message.text == "Пропустить" else message.text.strip()
    await state.update_data(interests=interests)
    await message.answer("Кого ты ищешь?", reply_markup=preferences_keyboard())
    await state.set_state(ProfileCreation.preferences)


@router.message(ProfileCreation.preferences)
async def fsm_preferences(message: Message, state: FSMContext) -> None:
    pref = _PREFS_MAP.get(message.text.strip())
    if not pref:
        await message.answer("Выбери один из вариантов:", reply_markup=preferences_keyboard())
        return
    await state.update_data(preferences=pref)
    await message.answer(
        "Напиши пару слов о себе — это привлечёт внимание!\n"
        "Или нажми «Пропустить»:",
        reply_markup=skip_keyboard(),
    )
    await state.set_state(ProfileCreation.bio)


@router.message(ProfileCreation.bio)
async def fsm_bio(message: Message, state: FSMContext) -> None:
    bio = None if message.text == "Пропустить" else message.text.strip()
    await state.update_data(bio=bio)
    await message.answer(
        "📸 Отправь своё фото для анкеты.\n"
        "Или нажми «Пропустить» — можно добавить позже:",
        reply_markup=skip_keyboard(),
    )
    await state.set_state(ProfileCreation.photo)


@router.message(ProfileCreation.photo)
async def fsm_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()

    try:
        profile = await backend_client.create_profile(
            {
                "telegram_id": message.from_user.id,
                "name": data["name"],
                "age": data["age"],
                "gender": data["gender"],
                "city": data["city"],
                "interests": data.get("interests"),
                "preferences": data.get("preferences"),
                "bio": data.get("bio"),
            }
        )
    except Exception as exc:
        logger.error("create_profile_error", error=str(exc))
        await message.answer("😔 Ошибка при создании анкеты. Попробуй /profile ещё раз.")
        await state.clear()
        return

    # Загружаем фото если прислали
    if message.photo:
        try:
            bot: Bot = message.bot
            photo_file = await bot.get_file(message.photo[-1].file_id)
            photo_bytes = await bot.download_file(photo_file.file_path)
            await backend_client.upload_photo(message.from_user.id, photo_bytes.read())
        except Exception as exc:
            logger.warning("photo_upload_error", error=str(exc))

    await state.clear()
    await message.answer(
        f"✅ Анкета создана! Добро пожаловать в Dating Bot, {data['name']}! 🎉",
        reply_markup=main_menu_keyboard(),
    )


# ─────────────────────────────────────────────
# /browse — просмотр анкет
# ─────────────────────────────────────────────

@router.message(Command("browse"))
@router.message(lambda m: m.text == "❤️ Смотреть анкеты")
async def cmd_browse(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_next_profile(message, message.from_user.id)


async def _show_next_profile(message: Message, telegram_id: int) -> None:
    try:
        profile = await backend_client.get_next_profile(telegram_id)
    except Exception as exc:
        logger.error("browse_error", error=str(exc))
        await message.answer("😔 Ошибка при загрузке анкет. Попробуй позже.")
        return

    if not profile:
        await message.answer(
            "😔 Анкеты закончились. Загляни позже — появятся новые!",
            reply_markup=main_menu_keyboard(),
        )
        return

    await _render_profile_card(message, profile)


async def _render_profile_card(message: Message, profile: dict) -> None:
    gender_display = {"male": "Парень", "female": "Девушка", "other": "Другой"}.get(
        profile.get("gender", ""), "—"
    )
    text = (
        f"<b>{profile.get('name', '—')}, {profile.get('age', '—')}</b>\n"
        f"📍 {profile.get('city', '—')} · {gender_display}\n"
    )
    if profile.get("interests"):
        text += f"🎯 {profile['interests']}\n"
    if profile.get("bio"):
        text += f"\n{profile['bio']}"

    keyboard = browse_keyboard(profile["id"])
    photos = profile.get("photos", [])

    if photos:
        await message.answer_photo(photo=photos[0], caption=text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


# ─────────────────────────────────────────────
# Callbacks — лайк / скип при просмотре
# ─────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("like:"))
async def cb_like(callback: CallbackQuery) -> None:
    profile_id = int(callback.data.split(":")[1])
    try:
        await publish_action(
            from_telegram_id=callback.from_user.id,
            to_profile_id=profile_id,
            action="like",
        )
    except Exception as exc:
        logger.error("like_publish_error", error=str(exc))

    await callback.answer("❤️ Лайк!")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _show_next_profile(callback.message, callback.from_user.id)


@router.callback_query(lambda c: c.data and c.data.startswith("skip:"))
async def cb_skip(callback: CallbackQuery) -> None:
    profile_id = int(callback.data.split(":")[1])
    try:
        await publish_action(
            from_telegram_id=callback.from_user.id,
            to_profile_id=profile_id,
            action="skip",
        )
    except Exception as exc:
        logger.error("skip_publish_error", error=str(exc))

    await callback.answer("👎 Пропущено")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _show_next_profile(callback.message, callback.from_user.id)


@router.callback_query(lambda c: c.data == "stop_browse")
async def cb_stop_browse(callback: CallbackQuery) -> None:
    await callback.message.delete()
    await callback.message.answer("Главное меню:", reply_markup=main_menu_keyboard())
    await callback.answer()


# ─────────────────────────────────────────────
# Callbacks — редактирование анкеты
# ─────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "edit_profile")
async def cb_edit_profile(callback: CallbackQuery) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Что хочешь изменить?", reply_markup=edit_profile_keyboard())
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("edit:"))
async def cb_edit_field(callback: CallbackQuery, state: FSMContext) -> None:
    field = callback.data.split(":")[1]
    field_names = {
        "name": "имя",
        "age": "возраст",
        "city": "город",
        "bio": "описание",
        "interests": "интересы",
    }
    await state.update_data(editing_field=field)
    await state.set_state(ProfileEdit.editing_value)
    await callback.message.answer(
        f"Введи новое значение для поля «{field_names.get(field, field)}»:",
        reply_markup=remove_keyboard(),
    )
    await callback.answer()


@router.message(ProfileEdit.editing_value)
async def fsm_edit_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    field = data.get("editing_field")
    value: str | int = message.text.strip()

    if field == "age":
        try:
            value = int(value)
            if not (16 <= value <= 100):
                raise ValueError
        except ValueError:
            await message.answer("Введи корректный возраст (16–100):")
            return

    try:
        await backend_client.update_profile(message.from_user.id, {field: value})
    except Exception as exc:
        logger.error("update_profile_error", error=str(exc))
        await message.answer("😔 Ошибка при обновлении анкеты.")
        await state.clear()
        return

    await state.clear()
    await message.answer("✅ Анкета обновлена!", reply_markup=main_menu_keyboard())


# ─────────────────────────────────────────────
# Callbacks — навигация
# ─────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "how_it_works")
async def cb_how_it_works(callback: CallbackQuery) -> None:
    text = (
        "ℹ️ <b>Как это работает?</b>\n\n"
        "1. Заполни анкету — имя, возраст, интересы и фото\n"
        "2. Смотри анкеты других пользователей\n"
        "3. Ставь лайки ❤️ или пропускай 👎\n"
        "4. Если лайк взаимный — это мэтч! 🎉\n"
        "5. После мэтча можно начать общение\n\n"
        "Чем активнее ты — тем выше твоя анкета в списке у других."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="← Назад", callback_data="back_to_welcome")]]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(lambda c: c.data == "back_to_welcome")
async def cb_back_to_welcome(callback: CallbackQuery) -> None:
    text = "👋 Добро пожаловать в Dating Bot!\n\nДавай начнём 🙂"
    await callback.message.edit_text(text, reply_markup=welcome_keyboard(is_new=True))
    await callback.answer()


@router.callback_query(lambda c: c.data == "create_profile")
async def cb_create_profile(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text("✏️ Отлично! Как тебя зовут?")
    await state.set_state(ProfileCreation.name)
    await callback.answer()


@router.callback_query(lambda c: c.data == "browse_profiles")
async def cb_browse_profiles(callback: CallbackQuery) -> None:
    await callback.answer()
    await _show_next_profile(callback.message, callback.from_user.id)


@router.callback_query(lambda c: c.data == "my_profile")
async def cb_my_profile(callback: CallbackQuery) -> None:
    try:
        profile = await backend_client.get_profile(callback.from_user.id)
    except Exception:
        await callback.answer("Ошибка загрузки анкеты")
        return

    if not profile:
        await callback.message.edit_text("У тебя ещё нет анкеты. Используй /profile для создания.")
    else:
        gender_display = {"male": "Мужской", "female": "Женский", "other": "Другой"}.get(
            profile.get("gender", ""), "—"
        )
        text = (
            f"👤 <b>Твоя анкета</b>\n\n"
            f"<b>Имя:</b> {profile.get('name', '—')}\n"
            f"<b>Возраст:</b> {profile.get('age', '—')}\n"
            f"<b>Пол:</b> {gender_display}\n"
            f"<b>Город:</b> {profile.get('city', '—')}\n"
            f"<b>Интересы:</b> {profile.get('interests', '—')}\n"
            f"<b>О себе:</b> {profile.get('bio', '—')}\n\n"
            f"📊 Заполненность: {profile.get('completeness_score', 0):.0f}/100"
        )
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=profile_actions_keyboard())
    await callback.answer()


@router.callback_query(lambda c: c.data == "back_to_menu")
async def cb_back(callback: CallbackQuery) -> None:
    await callback.message.delete()
    await callback.answer()


# ─────────────────────────────────────────────
# Кнопки главного меню (текстовые)
# ─────────────────────────────────────────────

@router.message(lambda m: m.text == "👥 Пригласить друга")
async def menu_invite(message: Message) -> None:
    bot_info = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{message.from_user.id}"
    await message.answer(
        f"👥 Твоя реферальная ссылка:\n\n<code>{ref_link}</code>",
        parse_mode="HTML",
    )


@router.message(lambda m: m.text == "⚙️ Настройки")
async def menu_settings(message: Message) -> None:
    await message.answer("⚙️ Настройки появятся в следующем этапе.")
