# Dating Bot

**Автор:** Саралиева Гульсим

Telegram-бот для знакомств с трёхуровневой системой ранжирования анкет, кэшированием через Redis, асинхронной обработкой событий через RabbitMQ и фоновыми задачами на Celery.

---

## Статус этапов

| Этап | Описание | Статус |
|------|----------|--------|
| 1 | Планирование, архитектура, схема БД | ✅ |
| 2 | Telegram-бот, регистрация, реферальная система | ✅ |
| 3 | CRUD анкет, ранжирование, Redis-кэш, интеграция | ✅ |
| 4 | Celery, оптимизация БД, тесты, метрики, деплой | ✅ |

---

## Стек

| Слой | Технологии |
|------|-----------|
| Bot | Python 3.11, aiogram 3, httpx |
| Backend | FastAPI, SQLAlchemy 2 (async), Pydantic v2 |
| БД | PostgreSQL 15 |
| Кэш | Redis 7 |
| Очередь | RabbitMQ 3 (aio-pika) |
| Фон | Celery + Celery Beat |
| Хранилище | MinIO (S3-совместимый) |
| Метрики | Prometheus + prometheus-fastapi-instrumentator |
| Логи | structlog (JSON-формат) |
| Инфра | Docker Compose |

---

## Архитектура

```
Telegram User
      │
      ▼
  Bot Service  ──(HTTP)──►  Backend API (FastAPI)
      │                          │         │
      │                     PostgreSQL   Redis
      │                          │
      └──(publish)──► RabbitMQ ◄─┘
                          │
                     ┌────┴─────┐
                     ▼          ▼
              Celery Worker  Bot Consumer
              (рейтинги)     (уведомления
                              о мэтчах)
                                │
                           Bot Service
                          (send_message)
```

**Два канала RabbitMQ:**
- `profile.actions` — бот публикует лайки/скипы → бэкенд обрабатывает
- `bot.notifications` — бэкенд публикует мэтч-события → бот отправляет уведомления

---

## Схема базы данных

```
users
  id, telegram_id, username, first_name, referrer_id→users, created_at

profiles
  id, user_id→users, name, age, gender, city,
  interests, preferences, bio, photo_count, completeness_score, created_at

profile_photos
  id, profile_id→profiles, s3_key, url, order_index

likes
  id, from_user_id→users, to_profile_id→profiles, is_skip, created_at
  idx: (to_profile_id, is_skip), (to_profile_id, is_skip, created_at)

matches
  id, user1_id→users, user2_id→users, created_at

ratings
  id, profile_id→profiles, level1_score, level2_score,
  referral_bonus, final_score, updated_at
  idx: (final_score)
```

---

## Алгоритм ранжирования

### Уровень 1 — Полнота анкеты (weight: 35%)

| Поле | Баллы |
|------|-------|
| Имя | +10 |
| Возраст | +10 |
| Город | +10 |
| Bio (>10 символов) | +15 |
| Интересы | +15 |
| Предпочтения | +10 |
| Пол | +5 |
| ≥1 фото | +15 |
| ≥3 фото | +10 (доп.) |

### Уровень 2 — Поведенческий (weight: 50%)

- лайки анкеты × 1.5 (макс 30)
- соотношение лайков к пропускам × 30 (макс 30)
- частота мэтчей × 20 (макс 20)
- лайки за последние 7 дней × 2 (макс 20)

### Уровень 3 — Реферальный бонус (weight: 15%)

- +5 баллов за каждого приглашённого (макс 25)

### Итоговая формула

```
final = level1 × 0.35 + level2 × 0.50 + referral_bonus × 0.15
```

Пересчёт происходит:
- при каждом лайке/скипе (инкрементально через RabbitMQ)
- ежечасно батчем (Celery Beat)

---

## Redis-кэш очереди просмотра

```
browse:{telegram_id}  — List, TTL 1ч    — очередь profile_id для выдачи
seen:{telegram_id}    — Set,  TTL 7д    — защита от дублей до записи лайка в БД
```

**Как работает:**
1. При старте сессии (или когда в очереди < 3 анкет) — подгружается 10 анкет, отсортированных по `final_score`, с учётом уже просмотренных из БД **и** Redis-сета.
2. Каждый `LPOP` из очереди сразу пишет id в `seen:{user_id}` — ещё до того как лайк дойдёт через RabbitMQ до БД.
3. При смене предпочтений или удалении анкеты оба ключа сбрасываются.

---

## API endpoints

```
GET  /health

POST /api/v1/users/register          — регистрация / повторный вход
GET  /api/v1/users/{telegram_id}     — получить пользователя

POST   /api/v1/profiles              — создать анкету
GET    /api/v1/profiles/{telegram_id}
PUT    /api/v1/profiles/{telegram_id}
DELETE /api/v1/profiles/{telegram_id}
POST   /api/v1/profiles/{telegram_id}/photos

GET  /api/v1/browse/{telegram_id}    — следующая анкета из кэша

GET  /metrics                        — Prometheus метрики
```

Swagger UI: **http://localhost:8000/docs**

---

## Функционал бота

| Команда / кнопка | Действие |
|-----------------|---------|
| `/start` | Регистрация, приветствие. Поддержка реф. ссылок: `/start ref_<id>` |
| `/profile` | Просмотр своей анкеты с рейтингом. Если нет — FSM создания |
| `/browse` | Листать анкеты с лайком ❤️ / пропуском 👎 |
| `/ref` | Получить реферальную ссылку |
| `⚙️ Настройки` | Сменить предпочтения поиска или удалить анкету |
| Мэтч | Уведомление с кликабельной ссылкой на собеседника |

---

## Тесты

```bash
cd tests && pip install -r requirements.txt
pytest ../tests/test_all.py -v
```

**Покрытие:**
- `TestUserService` — регистрация, повторный вход, рефералы, поиск (7 тестов)
- `TestHealthEndpoint` — /health (1 тест)
- `TestRegisterEndpoint` — регистрация через API, 422 валидация (5 тестов)
- `TestGetUserEndpoint` — GET /users, 404, поля ответа (3 теста)
- `TestKeyboards` — типы и кнопки клавиатур (6 тестов)
- `TestBackendClient` — health_check, register, get_user через mock (7 тестов)
- `TestRatingService` — создание записи, полная/минимальная анкета, пересчёт (4 теста)

---

## Локальный запуск

### Требования

- Docker и Docker Compose

### Шаги

```bash
# 1. Скопировать конфиг
cp .env.example .env

# 2. Вставить токен бота в .env
TELEGRAM_BOT_TOKEN=your_token_here

# 3. Запустить
docker compose up --build
```

### Доступные интерфейсы

| Сервис | URL | Логин |
|--------|-----|-------|
| Swagger UI | http://localhost:8000/docs | — |
| Prometheus метрики | http://localhost:9090 | — |
| RabbitMQ Management | http://localhost:15672 | guest / guest |
| MinIO Console | http://localhost:9001 | minioadmin / minioadmin |

### Структура проекта

```
tech-2026/
├── bot/
│   ├── main.py            — запуск polling, lifespan
│   ├── handlers.py        — все хендлеры и FSM
│   ├── keyboards.py       — Reply и Inline клавиатуры
│   ├── states.py          — FSM состояния
│   ├── api_client.py      — HTTP-клиент к backend
│   ├── mq_client.py       — публикация событий в RabbitMQ
│   ├── mq_consumer.py     — потребитель уведомлений о мэтчах
│   └── config.py
│
├── backend/
│   ├── main.py            — FastAPI app, lifespan, RabbitMQ consumer
│   ├── celery_app.py      — Celery + Beat (пересчёт рейтингов каждый час)
│   ├── api/routes/
│   │   ├── users.py
│   │   ├── profiles.py
│   │   └── browse.py
│   ├── services/
│   │   ├── user_service.py
│   │   ├── profile_service.py
│   │   ├── like_service.py    — лайки, мэтчи, RabbitMQ publish
│   │   ├── rating_service.py  — трёхуровневый рейтинг
│   │   └── cache_service.py   — Redis очередь + seen-сет
│   ├── models/            — SQLAlchemy ORM (user, profile, like, match, rating)
│   ├── schemas/           — Pydantic схемы
│   ├── core/              — config, logging, redis, rabbitmq, minio
│   └── db/session.py
│
├── tests/test_all.py
├── docker-compose.yml
└── prometheus.yml
```
