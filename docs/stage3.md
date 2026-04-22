# Dating Bot — Документация. Этап 3: Система анкет и ранжирования

**Проект:** tech-2026 | **Автор:** Саралиева Гульсим

---

## 1. Обзор Этапа 3

Третий этап расширяет базовую функциональность до полноценного рабочего потока: пользователь создаёт анкету, просматривает чужие анкеты, ставит лайки или пропускает — а система в фоне ранжирует анкеты и находит взаимные совпадения (мэтчи).

В рамках этапа реализовано:

- **CRUD анкет** — создание, просмотр, редактирование, загрузка фотографий в MinIO
- **FSM-флоу в боте** — пошаговое создание анкеты через машину состояний (8 шагов)
- **Алгоритм ранжирования (3 уровня)** — от заполненности анкеты до поведенческих сигналов
- **Кэширование в Redis** — подгрузка предварительно отранжированных анкет порциями
- **Интеграция через RabbitMQ** — лайки/скипы от бота, мэтч-уведомления от бэкенда
- **Обнаружение мэтчей** — проверка взаимного лайка, уведомление обоих пользователей

---

## 2. Изменения в структуре проекта

```
dating-bot/
├── backend/
│   ├── core/
│   │   ├── config.py          # + Redis, RabbitMQ, MinIO настройки
│   │   ├── redis_client.py    # NEW: async Redis клиент
│   │   ├── rabbitmq.py        # NEW: aio-pika publisher + consumer
│   │   └── minio_client.py    # NEW: S3-клиент для фотографий
│   ├── models/
│   │   ├── like.py            # NEW: таблица likes (лайки и скипы)
│   │   ├── match.py           # NEW: таблица matches (мэтчи)
│   │   └── rating.py          # NEW: таблица ratings (рейтинги анкет)
│   ├── schemas/
│   │   └── profile.py         # NEW: ProfileCreate, ProfileUpdate, ProfileResponse
│   ├── services/
│   │   ├── profile_service.py # NEW: CRUD анкет + расчёт completeness
│   │   ├── rating_service.py  # NEW: 3-уровневый алгоритм ранжирования
│   │   ├── cache_service.py   # NEW: Redis-очередь анкет для просмотра
│   │   └── like_service.py    # NEW: обработка лайков, создание мэтчей
│   └── api/routes/
│       ├── profiles.py        # NEW: CRUD + загрузка фото
│       └── browse.py          # NEW: следующая анкета с ранжированием
│
├── bot/
│   ├── states.py              # NEW: FSM-состояния для создания/редактирования
│   ├── mq_client.py           # NEW: публикация лайков/скипов в RabbitMQ
│   ├── mq_consumer.py         # NEW: приём мэтч-уведомлений из RabbitMQ
│   ├── handlers.py            # + FSM-флоу, browse, edit, match notify
│   ├── keyboards.py           # + клавиатуры gender, like/skip, edit
│   └── api_client.py          # + методы для анкет и browse
```

---

## 3. База данных — новые таблицы

### 3.1 Like

Хранит все взаимодействия пользователей с анкетами — как лайки, так и скипы.

```python
class Like(Base):
    __tablename__ = "likes"
    __table_args__ = (UniqueConstraint("from_user_id", "to_profile_id"),)

    id: Mapped[int]
    from_user_id: Mapped[int]   # FK → users.id, кто поставил
    to_profile_id: Mapped[int]  # FK → profiles.id, чья анкета
    is_skip: Mapped[bool]       # False = лайк, True = скип
    created_at: Mapped[datetime]
```

`UniqueConstraint` гарантирует, что один пользователь не сможет лайкнуть одну анкету дважды — даже если запрос придёт повторно.

### 3.2 Match

Создаётся, когда оба пользователя лайкнули друг друга.

```python
class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int]
    user1_id: Mapped[int]   # FK → users.id
    user2_id: Mapped[int]   # FK → users.id
    created_at: Mapped[datetime]
```

### 3.3 Rating

Хранит рассчитанный рейтинг для каждой анкеты. Обновляется каждый раз, когда кто-то ставит лайк или скип, а также при изменении самой анкеты.

```python
class Rating(Base):
    __tablename__ = "ratings"

    id: Mapped[int]
    profile_id: Mapped[int]       # FK → profiles.id, unique
    level1_score: Mapped[float]   # Первичный рейтинг (заполненность)
    level2_score: Mapped[float]   # Поведенческий рейтинг
    referral_bonus: Mapped[float] # Бонус за приглашённых друзей
    final_score: Mapped[float]    # Итоговый комбинированный рейтинг
    updated_at: Mapped[datetime]
```

---

## 4. Алгоритм ранжирования

Алгоритм состоит из трёх уровней, как описано в задании. Реализован в `backend/services/rating_service.py`.

### 4.1 Уровень 1 — Первичный рейтинг (заполненность анкеты)

Рассчитывается при создании и обновлении анкеты. Хранится в `profiles.completeness_score`.

| Поле | Баллы |
|---|---|
| Имя | +10 |
| Возраст | +10 |
| Пол | +5 |
| Город | +10 |
| О себе (> 10 символов) | +15 |
| Интересы | +15 |
| Предпочтения | +10 |
| Минимум 1 фото | +15 |
| Минимум 3 фото | +10 |
| **Итого** | **max 100** |

```python
def _calc_completeness(profile: Profile) -> float:
    score = 0.0
    if profile.name:       score += 10
    if profile.age:        score += 10
    if profile.gender:     score += 5
    if profile.city:       score += 10
    if profile.bio and len(profile.bio) > 10: score += 15
    if profile.interests:  score += 15
    if profile.preferences: score += 10
    if profile.photo_count >= 1: score += 15
    if profile.photo_count >= 3: score += 10
    return min(score, 100.0)
```

### 4.2 Уровень 2 — Поведенческий рейтинг

Динамически пересчитывается на основе взаимодействий других пользователей с анкетой.

```python
async def _calc_level2(self, profile_id: int, user_id: int) -> float:
    # Количество лайков анкеты
    likes_count = SELECT COUNT(*) FROM likes WHERE to_profile_id=X AND is_skip=False

    # Соотношение лайков и пропусков
    total = likes_count + skips_count
    like_ratio = likes_count / total  # 0.0 .. 1.0

    # Частота взаимных мэтчей
    match_count = SELECT COUNT(*) FROM matches WHERE user1_id=X OR user2_id=X
    match_rate = match_count / max(likes_count, 1)

    # Активность за последние 7 дней
    recent_likes = SELECT COUNT(*) WHERE created_at >= NOW() - 7 days

    score = (
        min(likes_count * 1.5, 30)  # вес лайков — макс 30
        + like_ratio * 30           # соотношение — макс 30
        + match_rate * 20           # конверсия в мэтчи — макс 20
        + min(recent_likes * 2, 20) # недавняя активность — макс 20
    )
    return min(score, 100.0)
```

| Компонент | Формула | Макс |
|---|---|---|
| Количество лайков | `likes × 1.5` | 30 |
| Соотношение лайков/скипов | `(likes / total) × 30` | 30 |
| Частота мэтчей | `(matches / likes) × 20` | 20 |
| Активность (7 дней) | `recent_likes × 2` | 20 |

### 4.3 Уровень 3 — Комбинированный рейтинг

Интегрирует первые два уровня по весовой модели и добавляет реферальный бонус.

```
final_score = Level1 × 0.35 + Level2 × 0.50 + referral_bonus × 0.15
```

**Реферальный бонус:** +5 баллов за каждого приглашённого пользователя, максимум 25.

```python
async def _calc_referral_bonus(self, user_id: int) -> float:
    referrals = SELECT COUNT(*) FROM users WHERE referrer_id = user_id
    return min(referrals * 5.0, 25.0)
```

Веса выбраны так, чтобы поведенческий рейтинг (50%) оказывал наибольшее влияние — это стимулирует активность в приложении.

### 4.4 Когда пересчитывается рейтинг

- При создании анкеты — инициализируется сразу
- При обновлении анкеты — пересчитывается `completeness_score` и `final_score`
- При загрузке нового фото — то же самое
- При каждом лайке или скипе **целевой** анкеты — пересчитывается `level2_score`

---

## 5. Кэширование анкет в Redis

При просмотре анкет важно не делать тяжёлый запрос к БД на каждое нажатие кнопки. Реализован механизм предзагрузки: когда пользователь открывает браузинг, система загружает 10 следующих анкет и кладёт их в Redis-список. Пользователь листает мгновенно — из кэша.

### 5.1 Структура кэша

```
Redis key:   browse:{telegram_id}
Type:        List
Value:       [profile_id_1, profile_id_2, ..., profile_id_10]
TTL:         3600 секунд (1 час)
```

### 5.2 Алгоритм подгрузки

```python
_REFILL_THRESHOLD = 3  # подгружаем, когда в очереди осталось < 3 анкет

async def get_next_profile(telegram_id):
    # 1. Если в очереди мало анкет — делаем новый запрос к БД
    if await cache_svc.needs_refill(telegram_id):
        ranked_ids = await rating_svc.get_ranked_profiles(
            for_user_id=user.id,
            own_profile_id=own_profile.id,
            gender_pref=gender_pref,
            limit=10,
        )
        await cache_svc.fill_queue(telegram_id, ranked_ids)

    # 2. Берём следующий ID из начала списка (LPOP)
    next_id = await cache_svc.get_next_profile_id(telegram_id)

    # 3. Загружаем полные данные анкеты из PostgreSQL
    return await profile_svc.get_by_id(next_id)
```

### 5.3 Исключения при ранжировании

При построении отсортированного списка система автоматически исключает:
- Уже просмотренные анкеты (есть запись в `likes`)
- Собственную анкету пользователя
- Анкеты не совпадающего пола (если задано предпочтение)

```python
# Все уже просмотренные
seen_ids = SELECT to_profile_id FROM likes WHERE from_user_id = me

# Итоговый запрос: профили, отсортированные по рейтингу
SELECT profiles.id, ratings.final_score
FROM profiles
LEFT JOIN ratings ON ratings.profile_id = profiles.id
WHERE profiles.id NOT IN (seen_ids)
  AND profiles.gender = preferred_gender  -- если указано
ORDER BY ratings.final_score DESC NULLS LAST
LIMIT 10
```

---

## 6. Интеграция через RabbitMQ

Для взаимодействия между ботом и бэкендом используется **RabbitMQ** — брокер сообщений. Это позволяет развязать сервисы: бот не ждёт ответа на каждое нажатие кнопки, а просто публикует событие.

### 6.1 Две очереди

| Очередь | Направление | Содержимое |
|---|---|---|
| `profile.actions` | Bot → Backend | Лайк или скип |
| `bot.notifications` | Backend → Bot | Уведомление о мэтче |

### 6.2 Поток лайка

```
Пользователь нажимает ❤️
    ↓
Bot: publish_action(from_telegram_id=111, to_profile_id=42, action="like")
    ↓
RabbitMQ: очередь profile.actions
    ↓
Backend consumer: _handle_action_event(payload)
    ↓
LikeService.process_action():
    1. Сохраняем Like в БД
    2. Пересчитываем рейтинг анкеты 42
    3. Проверяем взаимный лайк:
       SELECT * FROM likes
       WHERE from_user_id = owner_of_profile_42
         AND to_profile_id = own_profile_of_111
         AND is_skip = False
    4. Если взаимный → создаём Match, публикуем в bot.notifications
    ↓
Bot consumer: handle_match_notification()
    ↓
bot.send_message(user1): "🎉 Мэтч с Алиса!"
bot.send_message(user2): "🎉 Мэтч с Иван!"
```

### 6.3 Инициализация в бэкенде

```python
# backend/main.py — lifespan
await init_rabbitmq()
await consume(QUEUE_ACTIONS, _handle_action_event)  # фоновый потребитель
```

### 6.4 Инициализация в боте

```python
# bot/main.py — запуск
await init_mq()                                           # publisher
asyncio.create_task(start_notification_consumer(bot))     # consumer в фоне
await dp.start_polling(bot)                               # основной polling
```

Бот запускает три параллельных asyncio-задачи: Telegram polling, потребитель уведомлений и publisher готов к использованию по требованию.

---

## 7. Загрузка фотографий в MinIO

MinIO — это S3-совместимое хранилище, развёрнутое локально в Docker. Используется для хранения фотографий анкет.

### 7.1 Структура ключей

```
Бакет:   dating-photos
Ключ:    {telegram_id}/{uuid4}.jpg

Пример:  dating-photos/123456789/f47ac10b-58cc-4372-a567-0e02b2c3d479.jpg
```

### 7.2 Поток загрузки фото

```
Пользователь отправляет фото в боте
    ↓
Bot: скачивает байты через bot.download_file()
    ↓
POST /api/v1/profiles/{telegram_id}/photos (multipart/form-data)
    ↓
Backend:
    1. Генерирует уникальный ключ: {telegram_id}/{uuid4}.jpg
    2. Загружает в MinIO через minio.put_object()
    3. Сохраняет в ProfilePhoto: { s3_key, url, order_index }
    4. Увеличивает profile.photo_count
    5. Пересчитывает completeness_score и rating
```

MinIO вызывается через `asyncio.to_thread()`, так как официальный клиент синхронный — это позволяет не блокировать event loop.

---

## 8. FSM — создание анкеты в боте

FSM (Finite State Machine) — машина состояний из aiogram 3. Позволяет вести диалог с пользователем пошагово, сохраняя промежуточные данные в `FSMContext`.

### 8.1 Состояния

```python
class ProfileCreation(StatesGroup):
    name        = State()  # Шаг 1: имя
    age         = State()  # Шаг 2: возраст
    gender      = State()  # Шаг 3: пол (кнопки)
    city        = State()  # Шаг 4: город
    interests   = State()  # Шаг 5: интересы (или Пропустить)
    preferences = State()  # Шаг 6: кого ищешь (кнопки)
    bio         = State()  # Шаг 7: о себе (или Пропустить)
    photo       = State()  # Шаг 8: фото (или Пропустить)
```

### 8.2 Поток создания

```
/profile или кнопка "Заполнить анкету"
    ↓ нет анкеты
Бот: "Как тебя зовут?" → state = ProfileCreation.name
    ↓
Имя → state = .age → "Сколько тебе лет?"
    ↓
Возраст (16–100) → state = .gender → клавиатура [Мужской / Женский / Другой]
    ↓
Пол → state = .city → "В каком городе?"
    ↓
Город → state = .interests → "Расскажи об интересах [Пропустить]"
    ↓
Интересы → state = .preferences → [Ищу девушку / Ищу парня / Не важно]
    ↓
Предпочтения → state = .bio → "Напиши о себе [Пропустить]"
    ↓
Bio → state = .photo → "Отправь фото [Пропустить]"
    ↓
POST /api/v1/profiles  → создаём анкету в БД
POST /api/v1/profiles/{id}/photos  → если прислали фото
    ↓
"✅ Анкета создана!" + главное меню
```

### 8.3 Редактирование

После создания анкеты пользователь может изменить отдельные поля. В `handlers.py` реализован обработчик, который принимает inline-кнопку с именем поля, ждёт ввода и вызывает `PUT /api/v1/profiles/{telegram_id}`.

```python
class ProfileEdit(StatesGroup):
    choosing_field = State()
    editing_value  = State()
```

---

## 9. API — новые эндпоинты

### Анкеты

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/api/v1/profiles` | Создать анкету |
| `GET` | `/api/v1/profiles/{telegram_id}` | Получить свою анкету |
| `PUT` | `/api/v1/profiles/{telegram_id}` | Обновить анкету |
| `DELETE` | `/api/v1/profiles/{telegram_id}` | Удалить анкету |
| `POST` | `/api/v1/profiles/{telegram_id}/photos` | Загрузить фото |

### Просмотр

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/api/v1/browse/{telegram_id}` | Следующая анкета для просмотра |

**GET `/api/v1/browse/{telegram_id}`**

Внутри — полный цикл: проверка Redis-кэша, при необходимости подгрузка 10 следующих анкет через ранжирование, возврат первой из очереди с `rating_score`.

```json
{
  "id": 7,
  "name": "Алиса",
  "age": 23,
  "gender": "female",
  "city": "Алматы",
  "interests": "кино, йога",
  "bio": "Люблю путешествовать",
  "photo_count": 2,
  "photos": ["http://minio:9000/dating-photos/..."],
  "completeness_score": 75.0,
  "rating_score": 61.4
}
```

---

## 10. Поток данных — полный цикл лайка и мэтча

```
Алиса (id=111) листает анкеты
    ↓
GET /api/v1/browse/111
  → Redis: queue[111] = [7, 12, 3, ...]
  → Возвращает профиль Ивана (id=7)
    ↓
Алиса нажимает ❤️
    ↓
Bot → RabbitMQ: { action: "like", from: 111, to_profile: 7 }
    ↓
Backend consumer → LikeService:
  INSERT INTO likes (from_user_id=Алиса, to_profile_id=7, is_skip=False)
  RatingService: пересчитать рейтинг профиля 7
  Проверка: лайкал ли Иван анкету Алисы?
    → SELECT likes WHERE from_user=Иван AND to_profile=Алиса_profile
    → Да! Взаимный лайк.
  INSERT INTO matches (user1=Алиса, user2=Иван)
  Publish → bot.notifications: { type: "match", user1: 111, user2: 222 }
    ↓
Bot consumer:
  bot.send_message(111): "🎉 Мэтч с Иваном!"
  bot.send_message(222): "🎉 Мэтч с Алисой!"
```

---

## 11. Инфраструктура — изменения

### 11.1 Новые зависимости

**backend/requirements.txt:**

| Пакет | Назначение |
|---|---|
| `redis[asyncio]` | Async Redis клиент |
| `aio-pika` | Async RabbitMQ клиент (AMQP) |
| `minio` | MinIO/S3 клиент |
| `python-multipart` | Загрузка файлов через FastAPI |

**bot/requirements.txt:**

| Пакет | Назначение |
|---|---|
| `aio-pika` | Публикация событий и приём уведомлений |

### 11.2 Переменные окружения

В `.env` добавлена переменная:

```env
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
```

В `backend/core/config.py` добавлены поля:

```python
redis_url:         "redis://redis:6379/0"
rabbitmq_url:      "amqp://guest:guest@rabbitmq:5672/"
minio_endpoint:    "minio:9000"
minio_access_key:  "minioadmin"
minio_secret_key:  "minioadmin"
minio_bucket:      "dating-photos"
```

### 11.3 Запуск

```bash
docker compose up --build
```

| Сервис | URL | Описание |
|---|---|---|
| Backend API | http://localhost:8000/docs | Swagger UI — все эндпоинты |
| RabbitMQ UI | http://localhost:15672 | Мониторинг очередей (guest/guest) |
| MinIO Console | http://localhost:9001 | Просмотр загруженных фото (minioadmin/minioadmin) |

---

## 12. Логирование — новые события

| Событие | Сервис | Описание |
|---|---|---|
| `profile_created` | backend | Новая анкета создана |
| `profile_updated` | backend | Анкета обновлена |
| `rating_calculated` | backend | Рейтинг пересчитан (level1, level2, final) |
| `profile_liked` | backend | Пользователь поставил лайк |
| `profile_skipped` | backend | Пользователь пропустил |
| `match_created` | backend | Создан мэтч |
| `browse_cache_filled` | backend | В Redis загружено N анкет |
| `browse_cache_cleared` | backend | Кэш сброшен (после обновления анкеты) |
| `mq_consumer_started` | backend | Потребитель очереди запущен |
| `action_published` | bot | Лайк/скип отправлен в RabbitMQ |
| `match_notified` | bot | Уведомления о мэтче отправлены |

Пример лога при пересчёте рейтинга:

```
2025-04-21T10:15:32Z [info] rating_calculated
    profile_id=7
    level1=75.0
    level2=42.5
    referral_bonus=10.0
    final=61.375
    logger=services.rating_service
```

---

## 13. Следующие этапы

- **Этап 4** — Celery для регулярного массового пересчёта рейтингов, Prometheus-метрики на ключевых операциях, тестирование, оптимизация запросов к БД (индексы, денормализация)
