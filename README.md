# Сервис анализа проектной документации

**Версия:** 2.1.0 (добавлена поддержка OpenRouter)

## Описание

Микросервисная система для автоматического анализа соответствия проектной документации требованиям технического задания (ТЗ) и технических условий (ТУ).

Система использует большие языковые модели через:
- **Google Gemini API** (по умолчанию)
- **OpenRouter** (альтернативный провайдер)

## 🏗️ Архитектура

Система состоит из двух независимых сервисов, работающих в Docker.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Корпоративная сеть                              │
│                                                                        │
│  ┌────────────────────┐                                               │
│  │   Пользователь     │                                               │
│  └─────────┬──────────┘                                               │
│            │ HTTP                                                     │
│            ▼                                                           │
│  ┌────────────────────┐          HTTP           ┌──────────────────┐   │
│  │   Gradio UI        │ ─────────────────────► │   API Service    │   │
│  │  (БЕЗ прокси)      │                        │   (С прокси)     │   │
│  │  Port: 7861        │ ◄───────────────────── │   Port: 8002     │   │
│  └────────────────────┘       JSON              └─────────┬────────┘   │
│                                                           │            │
└───────────────────────────────────────────────────────────┼────────────┘
                                                            │
                                              SOCKS5 Proxy  │ VPN
                                              172.17.0.1    │
                                              :10808        │
                                                            ▼
                                                ┌───────────────────────┐
                                                │ Google Gemini API /   │
                                                │   OpenRouter          │
                                                └───────────────────────┘
```

### Сервис 1: Gradio UI (`ui-service/`)

- **Назначение**: Веб-интерфейс для пользователей.
- **Сеть**: Корпоративная сеть (БЕЗ прокси).
- **Порт**: 7861
- **Функции**:
  - Загрузка файлов (docx, pdf).
  - Выбор параметров анализа.
  - Отображение результатов в Markdown.
  - Обращение к API-сервису по HTTP.

### Сервис 2: API Service (`api-service/`)

- **Назначение**: Обработка запросов через AI провайдера.
- **Сеть**: Через VPN/SOCKS5 прокси.
- **Порт**: 8002
- **Функции**:
  - Прием запросов от UI.
  - Формирование промптов для AI.
  - **Поддержка двух режимов работы:**
    1. **`gemini`**: Использует нативный Gemini File API для мультимодального анализа.
    2. **`openrouter`**: Сначала извлекает текст из файлов с помощью Gemini, затем отправляет его для анализа на выбранную модель в OpenRouter.
  - Возврат JSON с результатами анализа.

## 🔐 Сетевая безопасность

| Компонент | Прокси | IP/Домен | Назначение |
|-----------|--------|----------|------------|
| **Gradio UI** | ❌ НЕТ | `0.0.0.0:7861` | Доступен из корпоративной сети |
| **API Service** | ✅ ДА | `172.17.0.1:10808` | SOCKS5 для доступа к внешним API |
| **Gemini/OpenRouter** | - | через VPN | Внешние сервисы |

**❗ ВАЖНО:** Проверьте IP-адрес вашего SOCKS5 прокси перед запуском!

## 📁 Структура проекта

> ⚠️ **Важное замечание:** Файлы `doc_analysis_app.py`, `Dockerfile` и `requirements.txt` в корневом каталоге являются частью старой монолитной архитектуры и **не используются**.

```
doc-analysis-service/
├── api-service/                  # ✅ Актуальный API-сервис (FastAPI)
│   ├── analysis_api.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example              # ✅ Пример файла с переменными окружения
│
├── ui-service/                   # ✅ Актуальный UI-сервис (Gradio)
│   ├── gradio_ui.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── docker-compose.yml           # ✅ Оркестратор микросервисов
├── doc_analysis_app.py          # ❌ Устаревший монолит
├── Dockerfile                   # ❌ Устаревший Dockerfile
├── requirements.txt             # ❌ Устаревшие зависимости
├── .gitignore
└── README.md
```

## 🚀 Быстрый старт

### Шаг 1: Настройка переменных окружения

1.  Создайте файл `.env` в директории `api-service/` на основе примера:
    ```bash
    cp api-service/.env.example api-service/.env
    ```

2.  Откройте `api-service/.env` и добавьте ваши ключи. **`GEMINI_API_KEY` обязателен всегда.**

    ```env
    # "gemini" или "openrouter"
    AI_PROVIDER=gemini

    # Ключ для Google Gemini API (ОБЯЗАТЕЛЕН для обоих провайдеров)
    GEMINI_API_KEY=ваш_ключ_gemini

    # Модель для Gemini
    GEMINI_MODEL=gemini-1.5-flash

    # --- Настройки для OpenRouter (если AI_PROVIDER=openrouter) ---
    # Ключ для OpenRouter API
    OPENROUTER_API_KEY=ваш_ключ_openrouter

    # Модель в OpenRouter (например, google/gemini-1.5-flash, anthropic/claude-3-haiku)
    OPENROUTER_MODEL=google/gemini-1.5-flash

    # Общая настройка "креативности" модели
    TEMPERATURE=0.1
    ```

### Шаг 2: Проверка SOCKS прокси

Откройте `docker-compose.yml` и проверьте IP-адрес прокси:
```yaml
environment:
  - HTTPS_PROXY=socks5://172.17.0.1:10808  # ← Проверьте этот адрес
  - HTTP_PROXY=socks5://172.17.0.1:10808
```

### Шаг 3: Запуск системы

```bash
docker-compose up -d --build
```

### Шаг 4: Проверка статуса

```bash
# Проверка запущенных контейнеров
docker-compose ps

# Логи API-сервиса
docker-compose logs -f doc-analysis-api

# Логи UI-сервиса
docker-compose logs -f doc-analysis-ui
```

### Шаг 5: Доступ к интерфейсу

Откройте в браузере:
- **Gradio UI:** http://localhost:7861
- **API Docs:** http://localhost:8002/docs

## 📋 Использование

Интерфейс Gradio интуитивно понятен:
1.  **Загрузите файлы**: ТЗ, проектную документацию и (при необходимости) ТУ.
2.  **Выберите параметры**: стадию документации и тип анализируемых требований.
3.  **Нажмите "Выполнить анализ"**.

Результаты появятся в виде Markdown-таблицы с детальным разбором каждого требования и общей сводкой.

## 🔧 Конфигурация

### API-сервис (`api-service/.env`)

Подробное описание переменных находится в разделе "Быстрый старт". Ключевой параметр — `AI_PROVIDER`, который определяет логику работы сервиса.

### Docker Compose

**Для API-сервиса (с прокси):**
```yaml
doc-analysis-api:
  environment:
    - HTTPS_PROXY=socks5://172.17.0.1:10808
    - HTTP_PROXY=socks5://172.17.0.1:10808
    - NO_PROXY=localhost,127.0.0.1,doc-analysis-ui
```

**Для UI-сервиса (без прокси):**
```yaml
doc-analysis-ui:
  environment:
    - API_SERVICE_URL=http://doc-analysis-api:8000
    # НЕТ ПРОКСИ!
```

## 📊 API Endpoints

### `GET /`
Health check API-сервиса.

**Ответ:**
```json
{
  "status": "ok",
  "service": "Document Analysis API",
  "provider": "gemini",
  "model": "gemini-1.5-flash"
}
```

### `POST /analyze`
Анализ документации. Принимает данные в формате `multipart/form-data`.

**Параметры формы:**
- `stage` (string): Стадия (e.g., "ФЭ").
- `req_type` (string): Тип требований (e.g., "ТЗ").
- `tz_document` (file): Файл технического задания.
- `doc_document` (file): Файл проектной документации.
- `tu_document` (file, optional): Файл технических условий.

**Пример ответа (JSON):**
```json
{
  "stage": "ФЭ",
  "req_type": "ТЗ",
  "requirements": [
    {
      "number": 1,
      "requirement": "Текст требования",
      "status": "Исполнено",
      "confidence": 95,
      "solution_description": "Описание решения",
      "reference": "Документ, стр. 12",
      "discrepancies": "",
      "recommendations": ""
    }
  ],
  "summary": "Общая сводка анализа"
}
```

## 🧪 Тестирование

### Тест API напрямую с помощью cURL

Создайте тестовые файлы `test_tz.txt` и `test_doc.txt`.

```bash
# Создаем простые текстовые файлы для теста
echo "Это тестовое ТЗ." > test_tz.txt
echo "Это тестовая документация." > test_doc.txt

# Отправляем запрос
curl -X POST http://localhost:8002/analyze \
  -F "stage=ФЭ" \
  -F "req_type=ТЗ" \
  -F "tz_document=@test_tz.txt" \
  -F "doc_document=@test_doc.txt"
```

### Тест прямого подключения к Gemini API из контейнера

Эта команда позволяет проверить, работает ли прокси и валиден ли `GEMINI_API_KEY`.

```bash
docker-compose exec doc-analysis-api python -c "
import os
import google.generativeai as genai
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
model = genai.GenerativeModel('gemini-1.5-flash')
response = model.generate_content('Привет!')
print(response.text)
"
```

## 📦 Зависимости

### API-сервис (`api-service/requirements.txt`)
- `fastapi`: Веб-фреймворк.
- `uvicorn`: ASGI сервер.
- `google-generativeai`: Клиент для Google Gemini API.
- `openai`: Клиент для OpenRouter (и других OpenAI-совместимых API).
- `python-dotenv`: Управление переменными окружения.
- `python-multipart`: Обработка `multipart/form-data` в FastAPI.

### UI-сервис (`ui-service/requirements.txt`)
- `gradio`: Создание веб-интерфейса.
- `requests`: HTTP-клиент для обращения к API.
- `python-dotenv`: Управление переменными окружения.

## 🤝 Вклад в разработку

1.  Форкните репозиторий.
2.  Создайте ветку фичи (`git checkout -b feature/amazing-feature`).
3.  Сделайте коммит (`git commit -m 'Add amazing feature'`).
4.  Запушьте (`git push origin feature/amazing-feature`).
5.  Откройте Pull Request.

## 📄 Лицензия

Проект создан для внутреннего использования.