# Сервис анализа проектной документации

**Версия:** 2.1.0

## Описание

Микросервисная система для автоматического анализа соответствия проектной документации требованиям технического задания (ТЗ) и технических условий (ТУ).

Система использует большие языковые модели (LLM) для анализа, поддерживая два провайдера:
- **Google Gemini API** (режим по умолчанию)
- **OpenRouter** (для доступа к широкому спектру моделей)

## Архитектура

Система построена на микросервисной архитектуре и состоит из двух независимых сервисов, управляемых через `docker-compose`.

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
│  │  (ui-service)      │                        │ (api-service)    │   │
│  │  Port: 7861        │ ◄───────────────────── │   Port: 8002     │   │
│  └────────────────────┘       JSON              └─────────┬────────┘   │
│                                                           │            │
└───────────────────────────────────────────────────────────┼────────────┘
                                                            │
                                              SOCKS5 Proxy  │ VPN
                                              (настраивается) │
                                                            ▼
                                                ┌───────────────────────┐
                                                │ Google Gemini API /   │
                                                │      OpenRouter       │
                                                └───────────────────────┘
```

### Компоненты

1.  **`ui-service` (Gradio UI)**
    *   **Назначение:** Пользовательский веб-интерфейс для загрузки документов и просмотра результатов анализа.
    *   **Технологии:** Gradio, Requests.
    *   **Сеть:** Работает в основной сети, доступен по порту `7861`. Не использует прокси.
    *   **Взаимодействие:** Отправляет HTTP-запросы на `api-service`.

2.  **`api-service` (FastAPI)**
    *   **Назначение:** Основная логика приложения. Обрабатывает файлы, формирует промпты и взаимодействует с LLM.
    *   **Технологии:** FastAPI, Google Gemini API, OpenAI-совместимый клиент.
    *   **Сеть:** Работает за SOCKS5 прокси для доступа к внешним API (Google, OpenRouter) через VPN.
    *   **Режимы работы:**
        *   `gemini`: Использует нативный Gemini File API для мультимодального анализа.
        *   `openrouter`: Извлекает текст из файлов с помощью Gemini, затем отправляет его для анализа на выбранную модель в OpenRouter.

## Структура проекта

```
doc-analysis-service/
├── api-service/                  # ✅ Сервис API (FastAPI)
│   ├── analysis_api.py           #    - Логика API
│   ├── requirements.txt          #    - Зависимости Python
│   ├── Dockerfile                #    - Docker-конфигурация
│   └── .env.example              #    - Пример файла с переменными окружения
│
├── ui-service/                   # ✅ Сервис UI (Gradio)
│   ├── gradio_ui.py              #    - Логика интерфейса
│   ├── requirements.txt          #    - Зависимости Python
│   └── Dockerfile                #    - Docker-конфигурация
│
├── docker-compose.yml            # ✅ Оркестратор для запуска всех сервисов
├── README.md                     # 📖 Этот файл
├── .gitignore
│
├── doc_analysis_app.py           # ❌ УСТАРЕЛО: Часть старой монолитной архитектуры
├── Dockerfile                    # ❌ УСТАРЕЛО: Dockerfile для монолита
└── requirements.txt              # ❌ УСТАРЕЛО: Зависимости для монолита
```
> **⚠️ Внимание:** Файлы `doc_analysis_app.py`, `Dockerfile` и `requirements.txt` в корневом каталоге являются частью старой архитектуры и **не используются**.

## Быстрый старт

### Шаг 1: Настройка переменных окружения

1.  Скопируйте файл с примером переменных окружения для API-сервиса:
    ```bash
    cp api-service/.env.example api-service/.env
    ```

2.  Откройте `api-service/.env` и укажите ваши API-ключи и настройки.

    ```env
    # Выбор провайдера: "gemini" или "openrouter"
    AI_PROVIDER=gemini

    # Ключ для Google Gemini API (ОБЯЗАТЕЛЕН для обоих режимов)
    # Используется для анализа файлов в режиме "gemini" и для извлечения текста в режиме "openrouter"
    GEMINI_API_KEY=ваш_ключ_gemini

    # Модель для Gemini (например, gemini-1.5-flash)
    GEMINI_MODEL=gemini-1.5-flash

    # --- Настройки для OpenRouter (используются, если AI_PROVIDER=openrouter) ---
    # Ключ для OpenRouter API
    OPENROUTER_API_KEY=ваш_ключ_openrouter

    # Модель в OpenRouter (например, google/gemini-1.5-flash, anthropic/claude-3-haiku)
    OPENROUTER_MODEL=google/gemini-1.5-flash

    # Общая настройка "креативности" модели (температура)
    TEMPERATURE=0.1
    ```

### Шаг 2: Настройка прокси

В файле `docker-compose.yml` проверьте и при необходимости измените адрес SOCKS5 прокси для сервиса `doc-analysis-api`.

```yaml
# docker-compose.yml

services:
  doc-analysis-api:
    # ...
    environment:
      - HTTPS_PROXY=socks5://172.17.0.1:10808  # ← Укажите правильный IP и порт вашего прокси
      - HTTP_PROXY=socks5://172.17.0.1:10808
      - NO_PROXY=localhost,127.0.0.1,doc-analysis-ui
```

### Шаг 3: Сборка и запуск

Выполните команду в корневой директории проекта:

```bash
docker-compose up -d --build
```
Эта команда соберёт образы для UI и API сервисов и запустит их в фоновом режиме.

### Шаг 4: Доступ к сервисам

-   **Веб-интерфейс (Gradio):** [http://localhost:7861](http://localhost:7861)
-   **Документация API (Swagger):** [http://localhost:8002/docs](http://localhost:8002/docs)

## Использование

1.  Откройте веб-интерфейс в браузере.
2.  Загрузите файлы: ТЗ, проектную документацию и (опционально) ТУ.
3.  Выберите параметры анализа: стадию документации и тип анализируемых требований.
4.  Нажмите кнопку **"Выполнить анализ"**.
5.  Результаты анализа появятся в интерфейсе в формате Markdown.

## Тестирование и отладка

### Проверка статуса контейнеров

```bash
# Показать запущенные контейнеры
docker-compose ps

# Просмотр логов API-сервиса в реальном времени
docker-compose logs -f doc-analysis-api

# Просмотр логов UI-сервиса
docker-compose logs -f doc-analysis-ui
```

### Тестирование API через cURL

Этот способ позволяет проверить работу API-сервиса напрямую, без UI.

1.  Создайте тестовые файлы:
    ```bash
    echo "Это тестовое ТЗ." > test_tz.txt
    echo "Это тестовая документация." > test_doc.txt
    ```

2.  Отправьте запрос на анализ:
    ```bash
    curl -X POST http://localhost:8002/analyze \
      -F "stage=ФЭ" \
      -F "req_type=ТЗ" \
      -F "tz_document=@test_tz.txt" \
      -F "doc_document=@test_doc.txt"
    ```

### Проверка доступа к Gemini API из контейнера

Эта команда позволяет убедиться, что прокси настроен верно и `GEMINI_API_KEY` валиден.

```bash
docker-compose exec doc-analysis-api python -c "
import os
import google.generativeai as genai
try:
    genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content('Привет!')
    print('Успешно! Ответ от Gemini API:')
    print(response.text)
except Exception as e:
    print(f'Ошибка подключения к Gemini API: {e}')
"
```

## API Endpoints

### `GET /`

-   **Описание:** Health check для API-сервиса.
-   **Ответ:** JSON с информацией о статусе, текущем провайдере и модели.
    ```json
    {
      "status": "ok",
      "service": "Document Analysis API",
      "provider": "gemini",
      "model": "gemini-1.5-flash"
    }
    ```

### `POST /analyze`

-   **Описание:** Основной эндпоинт для анализа документов. Принимает данные в формате `multipart/form-data`.
-   **Параметры формы:**
    -   `stage` (string): Стадия проекта (например, "ФЭ").
    -   `req_type` (string): Тип требований (например, "ТЗ").
    -   `tz_document` (file): Файл технического задания.
    -   `doc_document` (file): Файл проектной документации.
    -   `tu_document` (file, optional): Файл технических условий.
-   **Пример ответа (JSON):**
    ```json
    {
      "stage": "ФЭ",
      "req_type": "ТЗ",
      "requirements": [
        {
          "number": 1,
          "requirement": "Текст требования из ТЗ",
          "status": "Исполнено",
          "confidence": 95,
          "solution_description": "Краткое описание, как требование реализовано в документации.",
          "reference": "Ссылка на раздел/пункт документации, стр. X",
          "discrepancies": "Выявленные несоответствия (если есть).",
          "recommendations": "Рекомендации по устранению несоответствий (если есть)."
        }
      ],
      "summary": "Общая сводка по результатам анализа."
    }
    ```

## Лицензия

Проект создан для внутреннего использования.
