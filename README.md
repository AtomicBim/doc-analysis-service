# Сервис анализа проектной документации

## Описание

Микросервисная система для автоматического анализа соответствия проектной документации требованиям технического задания (ТЗ) и технических условий (ТУ) с использованием **Google Gemini API**.

## 🏗️ Архитектура

Система состоит из **двух независимых сервисов**:

```
┌──────────────────────────────────────────────────────────────────┐
│                    Корпоративная сеть                             │
│                                                                    │
│  ┌────────────────────┐                                           │
│  │   Пользователь     │                                           │
│  └─────────┬──────────┘                                           │
│            │ HTTP                                                 │
│            ▼                                                       │
│  ┌────────────────────┐          HTTP           ┌──────────────┐ │
│  │   Gradio UI        │ ─────────────────────► │  API Service │ │
│  │  (БЕЗ прокси)      │                        │  (С прокси)  │ │
│  │  Port: 7861        │ ◄───────────────────── │  Port: 8000  │ │
│  └────────────────────┘       JSON              └──────┬───────┘ │
│                                                         │          │
└─────────────────────────────────────────────────────────┼─────────┘
                                                          │
                                            SOCKS5 Proxy  │ VPN
                                            172.17.0.1    │
                                            :10808        │
                                                          ▼
                                                ┌─────────────────┐
                                                │  Google Gemini  │
                                                │      API        │
                                                └─────────────────┘
```

### Сервис 1: Gradio UI (`ui-service/`)

- **Назначение**: Веб-интерфейс для пользователей
- **Сеть**: Корпоративная сеть (БЕЗ прокси)
- **Порт**: 7861
- **Функции**:
  - Загрузка и валидация файлов (docx, pdf)
  - Выбор параметров анализа (стадия, тип требований)
  - Отображение результатов в Markdown
  - Обращение к API-сервису по HTTP

### Сервис 2: API Service (`api-service/`)

- **Назначение**: Обработка запросов через Google Gemini API
- **Сеть**: Через VPN/SOCKS5 прокси
- **Порт**: 8000
- **Функции**:
  - Прием запросов от UI
  - Формирование промптов для Gemini
  - Вызов Google Gemini API (через прокси)
  - Парсинг и структурирование результатов
  - Возврат JSON с анализом

## 🔐 Сетевая безопасность

| Компонент | Прокси | IP/Домен | Назначение |
|-----------|--------|----------|------------|
| **Gradio UI** | ❌ НЕТ | `0.0.0.0:7861` | Доступен из корпоративной сети |
| **API Service** | ✅ ДА | `172.17.0.1:10808` | SOCKS5 для Google Gemini API |
| **Gemini API** | - | через VPN | Внешний сервис Google |

**❗ ВАЖНО:** Проверьте IP-адрес вашего SOCKS5 прокси перед запуском!

## 📁 Структура проекта

> ⚠️ **Важное замечание:** Проект был переведен с монолитной архитектуры на микросервисную. Файлы `doc_analysis_app.py`, `Dockerfile` и `requirements.txt` в корневом каталоге являются частью старой версии и **не используются** в текущей конфигурации `docker-compose.yml`. Они сохранены для истории.

```
doc-analysis-service/
├── api-service/                  # ✅ Актуальный API-сервис (FastAPI + Gemini)
│   ├── analysis_api.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
├── ui-service/                   # ✅ Актуальный UI-сервис (Gradio)
│   ├── gradio_ui.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── docker-compose.yml           # ✅ Оркестратор микросервисов
├── doc_analysis_app.py          # ❌ Устаревший монолит (не используется)
├── Dockerfile                   # ❌ Устаревший Dockerfile для монолита
├── requirements.txt             # ❌ Устаревшие зависимости для монолита
├── .env.example
├── .gitignore
└── README.md
```

## 🚀 Быстрый старт

### Шаг 1: Настройка API ключа

1. Создайте файл `.env` в директории `api-service/`:
   ```bash
   cp api-service/.env.example api-service/.env
   ```

2. Откройте `api-service/.env` и добавьте ваш Gemini API ключ:
   ```env
   GEMINI_API_KEY=ваш_ключ_здесь
   GEMINI_MODEL=gemini-1.5-flash
   TEMPERATURE=0.1
   ```

### Шаг 2: Проверка SOCKS прокси

Откройте `docker-compose.yml` и проверьте IP прокси:
```yaml
environment:
  - HTTPS_PROXY=socks5://172.17.0.1:10808  # ← Проверьте этот адрес
  - HTTP_PROXY=socks5://172.17.0.1:10808
```

### Шаг 3: Запуск системы

```bash
cd doc-analysis-service
docker-compose up -d
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
- **API Docs:** http://localhost:8000/docs

## 📋 Использование

### 1. Загрузка файлов

- **Техническое задание (ТЗ)** - обязательно
- **Проектная документация** - обязательно
- **Технические условия (ТУ)** - для стадий РД и ПД

**Поддерживаемые форматы:** `.docx`, `.pdf`

### 2. Выбор параметров

**Стадии документации:**
- **ГК** - Градостроительная концепция
- **ФЭ** - Форэскизный проект
- **ЭП** - Эскизный проект
- **ПД** - Проектная документация (требуется ТУ)
- **РД** - Рабочая документация (требуется ТУ)

**Типы требований:**
- **ТЗ** - Техническое задание
- **ТУ_РД** - Технические условия для РД
- **ТУ_ПД** - Технические условия для ПД
- **ТУ_ФЭ** - Технические условия для ФЭ (встроенные)
- **ТУ_ЭП** - Технические условия для ЭП (встроенные)

### 3. Валидация файлов

Система автоматически проверяет:

**Формат:** только `.docx` и `.pdf`

**Имя файла** (должно содержать паттерн):

| Тип файла | Примеры имён |
|-----------|--------------|
| ТЗ | `tz_project.docx`, `тз_`, `техническое_задание` |
| Документация | `documentation_fe.pdf`, `docs_`, `проектная_документация` |
| ТУ | `requirements_tu.docx`, `_tu.pdf`, `технические_условия` |

### 4. Результаты

Результаты отображаются в виде **Markdown-таблицы**:

| № | Требование из ТЗ | Статус исполнения | Достоверность (%) | Описание решения | Ссылка | Несоответствия | Рекомендации |
|---|------------------|-------------------|-------------------|------------------|--------|----------------|--------------|

**Статусы:**
- ✅ **Исполнено** - полностью соответствует ТЗ
- ⚠️ **Частично исполнено** - есть отклонения
- ❌ **Не исполнено** - отсутствует в документации
- ❓ **Требует уточнения** - недостаточно данных

## 🔧 Конфигурация

### API-сервис (api-service/.env)

```env
# Google Gemini API ключ (ОБЯЗАТЕЛЬНО)
GEMINI_API_KEY=your_key_here

# Модель (опционально)
GEMINI_MODEL=gemini-1.5-flash

# Temperature (опционально)
TEMPERATURE=0.1
```

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

## 🛠️ Разработка

### Локальный запуск API-сервиса

```bash
cd api-service
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Создайте .env с GEMINI_API_KEY
python analysis_api.py
```

### Локальный запуск UI-сервиса

```bash
cd ui-service
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Укажите URL API
export API_SERVICE_URL=http://localhost:8000
python gradio_ui.py
```

## 📊 API Endpoints

### `GET /`
Health check API-сервиса

**Ответ:**
```json
{
  "status": "ok",
  "service": "Document Analysis API",
  "model": "gemini-1.5-flash"
}
```

### `POST /analyze`
Анализ документации

**Запрос:**
```json
{
  "stage": "ФЭ",
  "req_type": "ТЗ",
  "tz_document": {
    "filename": "tz_project.docx",
    "content_summary": "Содержимое ТЗ..."
  },
  "doc_document": {
    "filename": "documentation_fe.pdf",
    "content_summary": "Содержимое документации..."
  },
  "tu_document": null
}
```

**Ответ:**
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

## 🐛 Устранение неисправностей

### Проблема: API-сервис не доступен

```bash
# Проверьте статус
docker-compose ps

# Проверьте логи
docker-compose logs doc-analysis-api

# Перезапустите сервис
docker-compose restart doc-analysis-api
```

### Проблема: Ошибка "Connection refused" в UI

**Причина:** UI не может достучаться до API

**Решение:**
```bash
# Проверьте, что API запущен
curl http://localhost:8000/

# Проверьте переменную окружения в UI
docker-compose exec doc-analysis-ui env | grep API_SERVICE_URL
```

### Проблема: Gemini API не отвечает

**Причина:** Прокси не работает

**Решение:**
```bash
# Проверьте доступность прокси
curl --socks5 172.17.0.1:10808 https://generativelanguage.googleapis.com/

# Проверьте переменные прокси в API
docker-compose exec doc-analysis-api env | grep PROXY
```

### Проблема: "GEMINI_API_KEY не установлен"

**Решение:**
```bash
# Создайте файл .env
cp api-service/.env.example api-service/.env

# Добавьте ключ
echo "GEMINI_API_KEY=ваш_ключ" >> api-service/.env

# Перезапустите
docker-compose restart doc-analysis-api
```

## 📝 Примеры использования

### Пример 1: Анализ ФЭ с базовыми требованиями

```
Файлы:
- ТЗ: tz_project.docx
- Документация: documentation_fe.pdf

Параметры:
- Стадия: ФЭ
- Тип: ТУ_ФЭ (встроенные)

Результат: Таблица с анализом через Gemini API
```

### Пример 2: Анализ РД с внешними ТУ

```
Файлы:
- ТЗ: tz_rd.docx
- Документация: docs_project.pdf
- ТУ: requirements_tu.docx

Параметры:
- Стадия: РД
- Тип: ТУ_РД

Результат: Детальный анализ с учетом загруженных ТУ
```

## 🔒 Безопасность

- ✅ API ключи хранятся в `.env` (не коммитятся в Git)
- ✅ Файл `.env` монтируется read-only
- ✅ CORS настроен для ограничения доступа к API
- ✅ Прокси изолирует API-сервис от корпоративной сети
- ✅ Валидация всех входных файлов перед обработкой
- ✅ Healthchecks для мониторинга сервисов

## 📈 Масштабирование

### Горизонтальное масштабирование API

```yaml
doc-analysis-api:
  deploy:
    replicas: 3
```

### Load Balancer (nginx)

```nginx
upstream api_backend {
    server doc-analysis-api-1:8000;
    server doc-analysis-api-2:8000;
    server doc-analysis-api-3:8000;
}
```

## 🧪 Тестирование

### Тест API напрямую

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "stage": "ФЭ",
    "req_type": "ТЗ",
    "tz_document": {
      "filename": "test_tz.docx",
      "content_summary": "Тестовое ТЗ"
    },
    "doc_document": {
      "filename": "test_doc.pdf",
      "content_summary": "Тестовая документация"
    }
  }'
```

### Тест прокси

```bash
# Внутри контейнера API
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
- `fastapi` - веб-фреймворк
- `uvicorn` - ASGI сервер
- `google-generativeai` - Google Gemini API
- `pydantic` - валидация данных
- `httpx[socks]` - HTTP клиент с поддержкой SOCKS

### UI-сервис (`ui-service/requirements.txt`)
- `gradio` - веб-интерфейс
- `requests` - HTTP клиент
- `python-dotenv` - переменные окружения

## 🤝 Вклад в разработку

1. Форкните репозиторий
2. Создайте ветку фичи (`git checkout -b feature/amazing-feature`)
3. Сделайте коммит (`git commit -m 'Add amazing feature'`)
4. Запушьте (`git push origin feature/amazing-feature`)
5. Откройте Pull Request

## 📄 Лицензия

Проект создан для внутреннего использования.

---

**Версия:** 2.0.0 (Микросервисная архитектура)
**Дата:** 2025-10-06
**Статус:** ✅ Готов к использованию

**Технологии:**
- Google Gemini API (анализ)
- FastAPI (API backend)
- Gradio (веб-интерфейс)
- Docker Compose (оркестрация)
- SOCKS5 Proxy (VPN)
