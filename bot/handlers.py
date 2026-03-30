import structlog
from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from api_client import backend_client
from keyboards import main_menu_keyboard, welcome_keyboard, profile_actions_keyboard

router = Router()
logger = structlog.get_logger(__name__)


# ─────────────────────────────────────────────
# /start  —  точка входа, регистрация
# ─────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """
    Обрабатывает команду /start.

    Поддерживает реферальные ссылки вида:
        t.me/YourBot?start=ref_123456789
    где 123456789 — telegram_id пригласившего.

    Алгоритм:
    1. Парсим параметр команды — ищем реферера.
    2. Отправляем запрос регистрации в backend.
    3. Показываем персональное приветствие.
    """
    await state.clear()

    user = message.from_user
    referrer_telegram_id: int | None = None

    # Парсим реферальный параметр (например: /start ref_123456789)
    args = message.text.split(maxsplit=1)
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_telegram_id = int(args[1].replace("ref_", ""))
            logger.info("referral_detected", referrer_telegram_id=referrer_telegram_id)
        except ValueError:
            pass

    # Отправляем запрос регистрации в backend
    try:
        data = await backend_client.register_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            referrer_telegram_id=referrer_telegram_id,
        )
        is_new: bool = data.get("is_new", False)

        logger.info(
            "user_start",
            telegram_id=user.id,
            is_new=is_new,
            username=user.username,
        )

        # Приветствие зависит от того, новый ли пользователь
        if is_new:
            text = (
                f"👋 Привет, {user.first_name or 'незнакомец'}!\n\n"
                "Добро пожаловать в Dating Bot — место, где находят свою половинку.\n\n"
                "Давай начнём с заполнения анкеты — это займёт всего пару минут 🙂"
            )
        else:
            text = (
                f"С возвращением, {user.first_name or 'друг'}! 👋\n\n"
                "Рад снова тебя видеть. Что будем делать?"
            )

        await message.answer(
            text,
            reply_markup=welcome_keyboard(is_new),
        )

        # Показываем главное меню
        if not is_new:
            await message.answer(
                "Используй меню ниже для навигации:",
                reply_markup=main_menu_keyboard(),
            )

    except Exception as exc:
        logger.error("start_handler_error", telegram_id=user.id, error=str(exc))
        await message.answer(
            "😔 Произошла ошибка при подключении к серверу.\n"
            "Попробуй ещё раз через несколько секунд — /start"
        )


# ─────────────────────────────────────────────
# /help
# ─────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Справка по командам бота."""
    text = (
        "📖 <b>Команды бота:</b>\n\n"
        "/start — начать / перезапустить бота\n"
        "/profile — посмотреть или создать анкету\n"
        "/browse — смотреть анкеты других\n"
        "/ref — получить реферальную ссылку\n"
        "/help — эта справка\n\n"
        "По любым вопросам обращайся к администратору."
    )
    await message.answer(text, parse_mode="HTML")


# ─────────────────────────────────────────────
# /ref  —  реферальная ссылка
# ─────────────────────────────────────────────

@router.message(Command("ref"))
async def cmd_ref(message: Message) -> None:
    """Генерирует персональную реферальную ссылку."""
    bot_info = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{message.from_user.id}"
    await message.answer(
        f"👥 <b>Твоя реферальная ссылка:</b>\n\n"
        f"<code>{ref_link}</code>\n\n"
        "Поделись ею с друзьями — они получат приоритет в ранжировании, "
        "а ты — бонусные баллы в рейтинге! 🎯",
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────
# Текстовые кнопки главного меню
# ─────────────────────────────────────────────

@router.message(lambda m: m.text == "👤 Моя анкета")
async def menu_my_profile(message: Message) -> None:
    await message.answer(
        "👤 <b>Моя анкета</b>\n\n"
        "Здесь будет твой профиль. "
        "Функционал анкет появится в следующем этапе разработки.",
        parse_mode="HTML",
        reply_markup=profile_actions_keyboard(),
    )


@router.message(lambda m: m.text == "❤️ Смотреть анкеты")
async def menu_browse(message: Message) -> None:
    await message.answer(
        "❤️ <b>Просмотр анкет</b>\n\n"
        "Алгоритм ранжирования и просмотр анкет появятся в следующем этапе.",
        parse_mode="HTML",
    )


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


# ─────────────────────────────────────────────
# Callback кнопки (inline)
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
        "Чем активнее ты в системе — тем выше твоя анкета в списке других."
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад", callback_data="back_to_welcome")]
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(lambda c: c.data == "back_to_welcome")
async def cb_back_to_welcome(callback: CallbackQuery) -> None:
    text = (
        f"👋 Привет!\n\n"
        "Добро пожаловать в Dating Bot — место, где находят свою половинку.\n\n"
        "Давай начнём с заполнения анкеты — это займёт всего пару минут 🙂"
    )
    await callback.message.edit_text(text, reply_markup=welcome_keyboard(is_new=True))
    await callback.answer()


@router.callback_query(lambda c: c.data == "create_profile")
async def cb_create_profile(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "✏️ Создание анкеты появится в следующем этапе разработки.\n"
        "А пока изучи как работает бот — /help",
    )
    await callback.message.answer(
        "Используй меню для навигации:",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "browse_profiles")
async def cb_browse(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "❤️ Просмотр анкет появится в следующем этапе разработки."
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "my_profile")
async def cb_my_profile(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "👤 Просмотр анкеты появится в следующем этапе разработки.",
        reply_markup=profile_actions_keyboard(),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "back_to_menu")
async def cb_back(callback: CallbackQuery) -> None:
    await callback.message.delete()
    await callback.answer()
