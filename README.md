# Flight Bot — Telegram-бот горящих авиабилетов

Мониторинг цен на авиабилеты через Travelpayouts с уведомлениями в Telegram.

## Запуск

### 1. Клонировать репозиторий

```bash
git clone <repo-url>
cd flight_bot
```

### 2. Настроить переменные окружения

```bash
cp .env.example .env
```

Заполнить `.env`:
- `TELEGRAM_TOKEN` — токен бота от @BotFather
- `TRAVELPAYOUTS_TOKEN` — API-токен Travelpayouts
- `TRAVELPAYOUTS_MARKER` — партнёрский маркер Travelpayouts

### 3. Запустить контейнеры

```bash
docker-compose up -d
```

При первом запуске автоматически применяются миграции БД.

### 4. Загрузить справочники

```bash
docker-compose exec bot python -m bootstrap.load_references
```

Загрузит страны, города и аэропорты из Travelpayouts API.
Также выполняется автоматически при первом старте если таблица `countries` пуста.

### 5. Готово

Бот доступен в Telegram. Команды:
- `/start` — онбординг, выбор города вылета
- `/subscribe` — подписка на направление
- `/mysubscriptions` — список подписок
- `/unsubscribe` — удалить подписку
- `/settings` — порог уведомлений
- `/setorigin` — сменить город вылета

## Архитектура

- **bot** — Telegram long polling (aiogram 3.x)
- **scheduler** — мониторинг цен каждые 15 мин (APScheduler)
- **postgres** — PostgreSQL 15
- **redis** — кэш цен (Redis 7)
