# Dockerfile для API-сервиса с Google Gemini
FROM python:3.11-slim-bullseye

WORKDIR /app

# Копируем зависимости
COPY api-service/requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения (HYBRID VERSION)
COPY api-service/analysis_api_hybrid.py ./analysis_api.py
COPY api-service/config.py ./config.py

# Копируем папку с промптами
COPY prompts /prompts

# Порт для FastAPI
EXPOSE 8000

# Запуск API сервера
CMD ["python", "analysis_api.py"]
