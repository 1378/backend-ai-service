# Backend AI Service — сервис обработки контактных заявок с AI-интеграцией

## 📌 Общее описание

Это backend-сервис для обработки контактной формы с интеграцией искусственного интеллекта.

Сервис реализует полный цикл обработки запроса:

**запрос → валидация → защита от спама → AI-анализ → генерация ответа → отправка email → логирование → метрики**

Архитектура построена так, чтобы сервис можно было запускать локально без базы данных и без внешней инфраструктуры.

---

# ⚙️ 1. Как запустить проект

## 1.1 Требования

- Python 3.10+
- установленный pip
- (опционально) Ollama для локальной AI-модели

---

## 1.2 Установка зависимостей

```bash
python -m venv venv

Активировать окружение:

Windows:

venv\Scripts\activate

Linux / Mac:

source venv/bin/activate

Установить зависимости:

pip install -r requirements.txt
1.3 Настройка переменных окружения

Создать файл .env в корне проекта:

APP_NAME=Backend AI Service
API_PREFIX=/api/v1

# OpenAI (основной AI провайдер)
OPENAI_API_KEY=ваш_ключ
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini

# Ollama (локальный fallback AI)
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=mistral

# Email
OWNER_EMAIL=your_email@example.com

# =========================
# EMAIL (SMTP)
# =========================
EMAIL_PROVIDER=smtp

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASS=your_app_password
SMTP_FROM=your_email@gmail.com

# Rate limit
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=60
1.4 Запуск сервиса
1.4.1 Запуск Ollama (если используешь локальную модель)
ollama serve
ollama pull mistral
1.4.2 Запуск backend
python -m uvicorn app.main:app --reload
📡 2. Стек технологий
Backend
Python 3.10+
FastAPI (асинхронный веб-фреймворк)
Pydantic (валидация входных данных)
Uvicorn (ASGI сервер)
AI интеграция
OpenAI API (основной провайдер)
Ollama (локальный AI fallback)
Модели:
GPT-4o-mini
Mistral / Qwen (локальные модели)
Дополнительно
стандартная библиотека logging
json файловое хранилище
asyncio
🧠 3. Архитектура проекта
3.1 Структура
app/
 ├── main.py                # точка входа FastAPI
 ├── api/                   # HTTP маршруты
 ├── models/                # Pydantic модели (валидация)
 ├── services/              # бизнес-логика
 │    ├── contact_service   # основной оркестратор
 │    ├── ai_service        # AI логика (OpenAI + Ollama)
 │    ├── email_service     # отправка email
 │    ├── metrics_service   # метрики
 ├── repositories/          # файловое хранение
 ├── middleware/            # логирование
 ├── utils/                 # утилиты и ошибки
 ├── config.py              # конфигурация
3.2 Паттерны проектирования

Использованы:

Service Layer Pattern — вся бизнес-логика вынесена в сервисы
Dependency Injection — через FastAPI Depends
Repository Pattern (упрощённый) — файловое хранение данных
Fail-safe design — ошибки внешних сервисов не ломают основной поток
3.3 Почему такая архитектура

Выбор сделан в пользу:

простоты запуска (без БД)
модульности
возможности масштабирования (можно легко заменить JSON → PostgreSQL)
устойчивости к падению внешних API
📡 4. Реализация API
4.1 Эндпоинты
POST /api/v1/contact

Обработка контактной формы

Request:

{
  "name": "Иван",
  "phone": "+79999999999",
  "email": "test@gmail.com",
  "comment": "Хочу заказать сайт"
}

Response:

{
  "request_id": "uuid",
  "message": "Your contact request has been submitted successfully.",
  "sentiment": "positive",
  "auto_reply": "Спасибо за обращение...",
  "emails_sent": true
}
GET /api/v1/health

Проверка состояния сервиса

{ "status": "ok" }
GET /api/v1/metrics

Статистика обращений

{
  "total_submissions": 10,
  "positive": 5,
  "neutral": 3,
  "negative": 2,
  "last_updated": "2026-01-01T00:00:00Z"
}
4.2 Валидация

Используется Pydantic:

проверка email
ограничение длины текста
очистка входных данных
проверка формата телефона
4.3 Обработка ошибок
глобальный exception handler
429 при превышении rate limit
fallback при падении AI / email / логирования
сервис продолжает работу даже при отказе внешних компонентов
🧠 5. AI-интеграция
5.1 Используемые инструменты
OpenAI API — основной анализ и генерация
Ollama — локальный fallback (без интернета)
5.2 Логика fallback
OpenAI → ошибка → Ollama → ошибка → дефолтный ответ
5.3 Промпты
Анализ тональности
Определи тональность текста.
Ответь одним словом: positive, neutral или negative.

Текст: {text}
Генерация ответа
Напиши короткий профессиональный ответ пользователю {name}.
Сообщение: "{comment}"
Тональность: {sentiment}

Ответ должен быть:
- 2–3 предложения
- без заголовков
- без подписи
🛠️ 6. Что сделано с помощью AI

AI использовался как инструмент ускорения разработки:

Генерация:
шаблоны сервисов
базовая структура FastAPI
начальные версии AI промптов
Ручная доработка:
архитектура fallback цепочки
логирование и трассировка ошибок
rate limiting через файлы
обработка edge-case ошибок
стабилизация Ollama API
💾 7. Хранение данных
7.1 Логи
сохраняются в папку /logs
формат: структурированный текст
7.2 Метрики
файл: /data/metrics.json
обновляется при каждом запросе
7.3 Rate limiting
хранится в /data/rate_limit.json
алгоритм: sliding window
ключ: IP пользователя
защита от спама реализована без Redis/БД