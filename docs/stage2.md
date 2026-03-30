# Dating Bot — Документация. Этап 2: Базовая функциональность

**Проект:** tech-2026 | **Автор:** Саралиева Гульсим

---

## 1. Обзор Этапа 2

Второй этап охватывает разработку базовой функциональности системы: создание Telegram-бота, подключение его к Backend API, а также реализацию регистрации пользователей через команду `/start`.

В рамках этапа реализовано:

- **Telegram Bot Service** — интерфейс пользователя (aiogram 3)
- **Backend API** — FastAPI-сервер с бизнес-логикой
- **Регистрация пользователей** — сохранение Telegram ID при `/start`
- **Реферальная система** — передача `ref`-параметра в `/start`
- **Структурированное логирование** — structlog на стороне backend и bot
- **Docker Compose** — локальный запуск всей инфраструктуры

---

## 2. Структура проекта

Проект разделён на два независимых сервиса: `bot/` и `backend/`. Каждый запускается в отдельном Docker-контейнере.

```
dating-bot/
├── bot/
│   ├── main.py          # Точка входа бота, запуск polling
│   ├── handlers.py      # Обработчики команд и callback-кнопок
│   ├── api_client.py    # HTTP-клиент для общения с backend
│   ├── keyboards.py     # Клавиатуры Telegram (Reply + Inline)
│   ├── config.py        # Настройки бота (токен, URL backend)
│   ├── requirements.txt
│   └── Dockerfile
│
├── backend/
│   ├── main.py              # FastAPI приложение, middleware, роуты
│   ├── core/
│   │   ├── config.py        # Все настройки через pydantic-settings
│   │   └── logging.py       # Настройка structlog
│   ├── db/
│   │   └── session.py       # Движок БД, сессии, init_db()
│   ├── models/
│   │   ├── user.py          # SQLAlchemy модель User
│   │   └── profile.py       # SQLAlchemy модели Profile, ProfilePhoto
│   ├── schemas/
│   │   └── user.py          # Pydantic схемы для валидации
│   ├── services/
│   │   └── user_service.py  # Бизнес-логика регистрации
│   ├── api/routes/
│   │   └── users.py         # FastAPI роутер /api/v1/users
│   ├── requirements.txt
│   └── Dockerfile
│
├── docker-compose.yml
├── .env.example
└── .gitignore
```

---

## 3. Telegram Bot Service

### 3.1 Технологии

Бот написан на библиотеке **aiogram 3** — современном асинхронном фреймворке для Telegram Bot API. Все операции выполняются через `asyncio`, что позволяет обрабатывать тысячи пользователей без блокировок.

Зависимости:

- `aiogram==3.4.1` — фреймворк для Telegram-ботов
- `httpx==0.27.0` — асинхронный HTTP-клиент для запросов к backend
- `pydantic-settings` — управление настройками через `.env`
- `structlog` — структурированное логирование

### 3.2 Точка входа: `main.py`

Файл `main.py` запускает **polling** — бот подключается к серверам Telegram и начинает принимать обновления. Перед стартом выполняется health check backend.

```python
bot = Bot(token=bot_settings.telegram_bot_token)
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(router)

await bot.delete_webhook(drop_pending_updates=True)
await dp.start_polling(bot)
```

`MemoryStorage` используется для хранения состояний FSM (машины состояний). В production его заменит `RedisStorage` — данные сохранятся между перезапусками.

### 3.3 Обработчик `/start` и регистрация

Главный обработчик команды `/start` содержит всю логику первого взаимодействия:

- Парсит реферальный параметр — если пользователь перешёл по ссылке вида `/start ref_123456789`
- Вызывает `backend_client.register_user()` — отправляет POST-запрос в backend
- По флагу `is_new` в ответе показывает разное приветствие: новым — предлагает заполнить анкету, вернувшимся — перейти к просмотру
- При ошибке backend — выводит понятное сообщение вместо падения

```python
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    # Парсим реферальный параметр
    args = message.text.split(maxsplit=1)
    if len(args) > 1 and args[1].startswith("ref_"):
        referrer_telegram_id = int(args[1].replace("ref_", ""))

    # Регистрируем через backend
    data = await backend_client.register_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        referrer_telegram_id=referrer_telegram_id,
    )
    is_new = data.get("is_new", False)
```

### 3.4 API Client

Класс `BackendClient` инкапсулирует все HTTP-запросы к backend. Это правильный подход: если URL или структура запроса изменится — правим только одно место, а не все хендлеры.

```python
class BackendClient:
    async def register_user(self, telegram_id, username, ...) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/users/register",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
```

### 3.5 Клавиатуры

В боте используются два типа клавиатур:

- **`ReplyKeyboardMarkup`** — постоянное меню внизу экрана (Моя анкета, Смотреть анкеты, Настройки, Пригласить друга)
- **`InlineKeyboardMarkup`** — кнопки прямо под сообщением (Заполнить анкету, Как это работает, и т.д.)

---

## 4. Backend API (FastAPI)

### 4.1 Технологии

- **FastAPI** — современный асинхронный веб-фреймворк с автогенерацией документации
- **SQLAlchemy 2.0 async** — ORM с поддержкой async/await
- **asyncpg** — асинхронный PostgreSQL-драйвер
- **Pydantic v2** — валидация входных и выходных данных
- **structlog** — структурированные логи в JSON или консоль

### 4.2 Архитектура backend

Backend разделён по слоям — это стандартная практика для масштабируемых приложений:

```
HTTP Request
    ↓
FastAPI Router (api/routes/users.py)      ← валидация входных данных (Pydantic)
    ↓
Service Layer (services/user_service.py)  ← бизнес-логика
    ↓
Database (SQLAlchemy + asyncpg)           ← работа с PostgreSQL
    ↓
HTTP Response                             ← сериализация (Pydantic)
```

Такое разделение позволяет:

- Тестировать бизнес-логику отдельно от HTTP-слоя
- Легко заменять реализацию (например, сменить БД) без изменения роутеров
- Держать файлы маленькими и понятными

### 4.3 Модели базы данных

#### User

Таблица `users` хранит минимально необходимые данные о пользователе Telegram:

- `telegram_id` — уникальный идентификатор из Telegram (BigInteger, индексированный)
- `username` — @username (может отсутствовать, Telegram не обязывает его задавать)
- `first_name` — имя из профиля Telegram
- `referrer_id` — FK на `users.id`, указывает кто пригласил
- `created_at` — время регистрации, ставится автоматически через `server_default=func.now()`

```python
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None]
    first_name: Mapped[str | None]
    referrer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

#### Profile

Таблица `profiles` — анкета пользователя. Создаётся отдельно от `User`, так как пользователь может зарегистрироваться, но не сразу заполнить анкету.

- `completeness_score` — процент заполненности (0.0..1.0), влияет на рейтинг
- `photo_count` — количество фотографий, также влияет на рейтинг
- `interests` и `preferences` — хранятся как JSON-строки в Text-колонках

### 4.4 Сервис регистрации

`UserService.register()` реализует логику регистрации:

- **Идемпотентность** — если пользователь уже есть, возвращаем его данные без ошибки. Это важно: бот может вызвать `/start` повторно
- **Поиск реферера** — если передан `referrer_telegram_id`, ищем его в БД и сохраняем внутренний id
- **Флаг `is_new`** — `True` только при первой регистрации, бот использует его для разного приветствия
- **`db.flush()`** — получаем id нового пользователя до `commit()`, не прерывая транзакцию

```python
async def register(self, data: UserCreate) -> UserResponse:
    # Проверка идемпотентности
    existing = await self.get_by_telegram_id(data.telegram_id)
    if existing:
        return UserResponse.model_validate(existing)

    # Поиск реферера
    referrer_id = None
    if data.referrer_telegram_id:
        referrer = await self.get_by_telegram_id(data.referrer_telegram_id)
        if referrer:
            referrer_id = referrer.id

    # Создание пользователя
    user = User(telegram_id=data.telegram_id, referrer_id=referrer_id, ...)
    self.db.add(user)
    await self.db.flush()

    response = UserResponse.model_validate(user)
    response.is_new = True
    return response
```

### 4.5 API Endpoints

Доступные эндпоинты на текущем этапе:

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/api/v1/users/register` | Регистрация пользователя |
| `GET` | `/api/v1/users/{telegram_id}` | Получить пользователя по Telegram ID |
| `GET` | `/health` | Проверка работоспособности |
| `GET` | `/docs` | Swagger UI |
| `GET` | `/redoc` | ReDoc UI |

**POST `/api/v1/users/register`**

```
Body:     { telegram_id, username, first_name, referrer_telegram_id }
Response: { id, telegram_id, username, is_new, created_at, ... }
```

### 4.6 Middleware логирования

В FastAPI подключён middleware, который логирует каждый HTTP-запрос: метод, путь, статус ответа и время выполнения в миллисекундах. Это базовые метрики производительности без дополнительных инструментов.

```python
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000

    logger.info("http_request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round(duration_ms, 2),
    )
    return response
```

---

## 5. Инфраструктура (Docker Compose)

Все сервисы запускаются одной командой через `docker compose`. В `docker-compose.yml` описаны healthcheck-зависимости: backend стартует только когда PostgreSQL и Redis готовы принимать подключения.

| Сервис | Порты | Назначение |
|---|---|---|
| `postgres` | 5432 | Основная база данных |
| `redis` | 6379 | Кэширование анкет |
| `rabbitmq` | 5672 / 15672 | Очередь сообщений (+ UI) |
| `minio` | 9000 / 9001 | Хранилище фотографий (+ UI) |
| `backend` | 8000 | FastAPI API |
| `bot` | — | Telegram Bot polling |

### 5.1 Запуск проекта

1. Скопировать `.env.example` в `.env` и вставить токен бота
2. Запустить: `docker compose up --build`
3. Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
4. RabbitMQ Management UI: [http://localhost:15672](http://localhost:15672) (guest / guest)
5. MinIO Console: [http://localhost:9001](http://localhost:9001) (minioadmin / minioadmin)

---

## 6. Логирование

В проекте используется **structlog** — библиотека структурированного логирования. В отличие от обычного `logging`, structlog выводит логи в виде пар `ключ=значение`, что удобно для поиска и анализа в системах мониторинга (Grafana Loki, ELK и т.д.).

Пример лога при регистрации нового пользователя:

```
2024-01-15T10:23:45Z [info] user_registered
    telegram_id=123456789
    user_id=42
    referrer_id=None
    logger=services.user_service
```

Пример лога HTTP-запроса:

```
2024-01-15T10:23:45Z [info] http_request
    method=POST
    path=/api/v1/users/register
    status_code=200
    duration_ms=12.34
```

Логируемые события на текущем этапе:

| Событие | Где | Описание |
|---|---|---|
| `user_registered` | backend | Новый пользователь зарегистрирован |
| `user_already_exists` | backend | Повторный `/start` |
| `referrer_found` | backend | Найден реферер |
| `http_request` | backend | Каждый API-запрос с временем выполнения |
| `backend_not_available` | bot | Backend недоступен при старте бота |
| `start_handler_error` | bot | Ошибка в хендлере `/start` |

---

## 7. Поток данных при команде `/start`

```
Пользователь → /start ref_987654321
    ↓
Bot (handlers.py)
  1. Парсим "ref_987654321" → referrer_telegram_id = 987654321
  2. Вызываем backend_client.register_user(telegram_id=111, ...)
    ↓
HTTP POST /api/v1/users/register
    ↓
Backend (FastAPI)
  Router: валидация UserCreate через Pydantic
    ↓
  UserService.register():
    - SELECT users WHERE telegram_id = 111  → не найден
    - SELECT users WHERE telegram_id = 987654321 → referrer.id = 5
    - INSERT INTO users (telegram_id=111, referrer_id=5)
    - COMMIT
    - return UserResponse(is_new=True)
    ↓
HTTP 200 { "is_new": true, "id": 42, ... }
    ↓
Bot: показывает приветствие нового пользователя + кнопку "Заполнить анкету"
```

---

## 8. Следующие этапы

Этап 2 создаёт основу, на которую наращивается функциональность:

- **Этап 3** — CRUD анкет: создание, редактирование, загрузка фотографий в MinIO, алгоритм ранжирования (три уровня), кэширование в Redis
- **Этап 4** — Celery-задачи: регулярный пересчёт рейтингов, RabbitMQ для передачи событий лайков/пропусков/мэтчей, Prometheus + Grafana для метрик
