# Dockerfile для API-сервиса с Google Gemini
FROM python:3.11-slim-bullseye

WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY analysis_api.py .

# Порт для FastAPI
EXPOSE 8000

# Запуск API сервера
CMD ["python", "analysis_api.py"]
