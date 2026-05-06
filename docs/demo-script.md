# Сценарии демонстрации — защита этапа 4

Все команды выполняются из корня проекта `tech-2026/`.  
Твой telegram_id: `1672576797`, profile_id: `15`.

---

## 0. Запуск проекта (если не запущен)

```bash
docker compose up --build -d
docker compose ps          # убедиться что все 9 контейнеров Up
```

Ожидаемый вывод — все сервисы `Up`:
```
dating_backend, dating_bot, dating_postgres, dating_redis,
dating_rabbitmq, dating_minio, dating_celery_worker,
dating_celery_beat, dating_prometheus
```

---

## 1. Swagger UI — живая документация API

Открыть в браузере: **http://localhost:8000/docs**

**Показать:**
- эндпоинты `users`, `profiles`, `browse`
- выполнить прямо в браузере: `GET /api/v1/profiles/1672576797`
- в ответе показать поля `rating_score`, `completeness_score`, `photos`

---

## 2. PostgreSQL — схема и индексы

```bash
docker exec -it dating_postgres psql -U dating_user -d dating_db
```

**Таблицы:**
```sql
\dt
```

**Индексы на таблице likes (оптимизация запросов рейтинга):**
```sql
\d likes
```
Показать индексы `ix_likes_profile_skip` и `ix_likes_profile_skip_time`.

**Индекс на ratings (сортировка по рейтингу):**
```sql
\d ratings
```
Показать `ix_ratings_final_score`.

**Текущие рейтинги всех анкет:**
```sql
SELECT p.name, r.level1_score, r.level2_score, r.referral_bonus, r.final_score
FROM profiles p JOIN ratings r ON r.profile_id = p.id
ORDER BY r.final_score DESC;
```

**Выйти из psql:**
```sql
\q
```

---

## 3. Redis — кэш очереди просмотра

```bash
docker exec -it dating_redis redis-cli
```

**Посмотреть очередь после первого вызова browse:**
```bash
# В другом терминале сначала вызвать browse:
curl -s http://localhost:8000/api/v1/browse/1672576797 | python3 -m json.tool

# Затем в redis-cli:
LRANGE "browse:1672576797" 0 -1    # список оставшихся profile_id в очереди
SMEMBERS "seen:1672576797"         # set уже показанных
TTL "browse:1672576797"            # оставшееся время жизни (3600 сек)
```

**Объяснить:** каждый LPOP уменьшает очередь на 1. Когда остаётся < 3 — автоматическая дозагрузка следующих 10 анкет, отсортированных по `final_score`.

**Выйти:**
```
EXIT
```

---

## 4. Алгоритм ранжирования — три уровня

**Шаг 1.** Посмотреть текущие рейтинги:
```bash
docker exec dating_postgres psql -U dating_user -d dating_db -c "
SELECT p.name, p.age, p.city,
       r.level1_score  AS \"Уровень 1 (анкета)\",
       r.level2_score  AS \"Уровень 2 (поведение)\",
       r.referral_bonus AS \"Рефералы\",
       r.final_score   AS \"Итог\"
FROM profiles p JOIN ratings r ON r.profile_id = p.id
ORDER BY r.final_score DESC;"
```

**Шаг 2.** Симулировать лайк — поведенческий рейтинг должен вырасти:
```bash
# Пользователь 100000002 (Мария) лайкает анкету Александра (profile_id=5)
curl -s -u guest:guest -X POST http://localhost:15672/api/exchanges/%2F/amq.default/publish \
  -H "Content-Type: application/json" \
  -d '{"properties":{"delivery_mode":2},"routing_key":"profile.actions",
       "payload":"{\"action\":\"like\",\"from_telegram_id\":100000002,\"to_profile_id\":5}",
       "payload_encoding":"string"}'
```

**Шаг 3.** Проверить что `level2_score` у Александра вырос:
```bash
sleep 1
docker exec dating_postgres psql -U dating_user -d dating_db -c "
SELECT p.name, r.level1_score, r.level2_score, r.final_score
FROM profiles p JOIN ratings r ON r.profile_id = p.id
WHERE p.id = 5;"
```

---

## 5. RabbitMQ — асинхронная обработка событий

Открыть в браузере: **http://localhost:15672** (guest / guest)

**Показать:**
- вкладка Queues — очереди `profile.actions` и `bot.notifications`
- колонка `Ready` — сколько сообщений ждут обработки

**Симулировать взаимный лайк → мэтч:**
```bash
# Гульсим лайкает Марию (profile_id=6)
curl -s -u guest:guest -X POST http://localhost:15672/api/exchanges/%2F/amq.default/publish \
  -H "Content-Type: application/json" \
  -d '{"properties":{"delivery_mode":2},"routing_key":"profile.actions",
       "payload":"{\"action\":\"like\",\"from_telegram_id\":1672576797,\"to_profile_id\":6}",
       "payload_encoding":"string"}'

sleep 1

# Мария лайкает Гульсим (profile_id=15) — взаимный лайк → мэтч
curl -s -u guest:guest -X POST http://localhost:15672/api/exchanges/%2F/amq.default/publish \
  -H "Content-Type: application/json" \
  -d '{"properties":{"delivery_mode":2},"routing_key":"profile.actions",
       "payload":"{\"action\":\"like\",\"from_telegram_id\":100000002,\"to_profile_id\":15}",
       "payload_encoding":"string"}'
```

**Проверить что мэтч создался:**
```bash
docker exec dating_postgres psql -U dating_user -d dating_db -c "
SELECT m.id, u1.telegram_id AS user1, u2.telegram_id AS user2, m.created_at
FROM matches m
JOIN users u1 ON u1.id = m.user1_id
JOIN users u2 ON u2.id = m.user2_id
ORDER BY m.created_at DESC LIMIT 3;"
```

**В Telegram:** должно прийти сообщение "🎉 Мэтч!" с кликабельной ссылкой на Марию.

---

## 6. Celery — фоновый пересчёт рейтингов

**Запустить задачу вручную:**
```bash
docker exec dating_celery_worker \
  celery -A celery_app call celery_app.recalculate_all_ratings
```

**Посмотреть логи выполнения:**
```bash
docker logs dating_celery_worker --tail 20
```

Ожидаемый вывод:
```
rating_calculated  profile_id=5  level1=75.0  level2=...  final=...
...
ratings_batch_recalculated  updated=14  errors=0
Task celery_app.recalculate_all_ratings succeeded in 0.2s
```

**Показать расписание (каждый час):**
```bash
docker logs dating_celery_beat --tail 10
```

---

## 7. MinIO — хранилище фотографий

Открыть в браузере: **http://localhost:9001** (minioadmin / minioadmin)

**Показать:**
- бакет `dating-photos`
- файлы вида `{telegram_id}/{uuid}.jpg`

**Через API — pre-signed URL:**
```bash
curl -s http://localhost:8000/api/v1/profiles/1672576797 \
  | python3 -c "import sys,json; p=json.load(sys.stdin); print(p['photos'][0] if p['photos'] else 'нет фото')"
```
URL содержит `X-Amz-Expires=3600` — ссылка действует 1 час, потом истекает.

---

## 8. Метрики Prometheus

Открыть в браузере: **http://localhost:9090**

**Запросы для демонстрации:**
```
# Количество HTTP-запросов по эндпоинтам
http_requests_total

# Latency browse-эндпоинта (p95)
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{handler="/api/v1/browse/{telegram_id}"}[5m]))

# Количество запросов к /api/v1/browse
rate(http_requests_total{handler="/api/v1/browse/{telegram_id}"}[5m])
```

**Сырые метрики:**
```bash
curl -s http://localhost:8000/metrics | grep http_requests_total | head -10
```

---

## 9. Структурированные логи (structlog)

```bash
# Логи бэкенда — все события в JSON
docker logs dating_backend --tail 30

# Отфильтровать только события лайков и мэтчей
docker logs dating_backend 2>&1 | grep -E "liked|skipped|match_created"

# Логи бота
docker logs dating_bot --tail 20

# Логи Celery
docker logs dating_celery_worker --tail 20
```

**Показать:** каждая строка — JSON с полями `event`, `profile_id`, `by`, `timestamp`.

---

## 10. Тесты

```bash
cd tests && pip install -r requirements.txt -q
cd .. && python -m pytest tests/test_all.py -v
```

Ожидаемый вывод: `51 passed`.

**Что покрыто:**
- `TestUserService` — регистрация, рефералы, поиск (7 тестов)
- `TestRegisterEndpoint` / `TestGetUserEndpoint` — API + 422 валидация (8 тестов)
- `TestKeyboards` — типы и кнопки (6 тестов)
- `TestBackendClient` — HTTP-клиент через mock (7 тестов)
- `TestRatingService` — формула рейтинга, пересчёт (5 тестов)
- `TestLikeService` — лайки, скипы, мэтч, дубли (6 тестов)
- `TestCacheService` — очередь, дозагрузка, изоляция (7 тестов)
- `TestBrowseEndpoint` — выдача анкет, 400/404 (4 теста)

---

## 11. Бот — живая демонстрация

Последовательность действий в Telegram:

1. `/start` → регистрация, приветствие
2. `👤 Моя анкета` → показать анкету с `completeness_score` и `rating_score`
3. `❤️ Смотреть анкеты` → листать, показать что каждая следующая анкета подгружается быстро (из Redis)
4. `⚙️ Настройки` → сменить предпочтения поиска
5. `/ref` → показать реферальную ссылку
6. Объяснить: если открыть ссылку с другого аккаунта — `referrer_id` запишется и даст +5 к рейтингу

---

## Быстрая шпаргалка — ответы на вопросы

| Вопрос | Ответ |
|--------|-------|
| Зачем Redis если есть PostgreSQL? | SQL-запрос на сборку очереди ~50 мс, LPOP из Redis ~1 мс. При каждом свайпе разница ощутима |
| Зачем RabbitMQ если можно HTTP? | Бот не ждёт бэкенд → мгновенный отклик. Очередь буферизует нагрузку и не теряет сообщения |
| Зачем Celery если есть пересчёт по событию? | Батч нужен чтобы снижать `level2_score` у неактивных анкет — это не триггерится событием |
| Зачем MinIO если можно хранить URL из Telegram? | Telegram удаляет file_id через некоторое время. MinIO — постоянное хранилище под нашим контролем |
| Зачем индексы в моделях? | Без `ix_likes_profile_skip` подсчёт лайков — Seq Scan по всей таблице. С индексом — Index Scan |
| Почему seen-сет в Redis? | Лайк пишется в БД через RabbitMQ асинхронно. Без сета анкеты дублировались при пересборке очереди |
