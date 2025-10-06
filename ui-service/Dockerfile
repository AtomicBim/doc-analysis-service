# Dockerfile для Gradio UI (БЕЗ прокси)
FROM python:3.11-slim-bullseye

WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY gradio_ui.py .

# Порт для Gradio
EXPOSE 7861

# Запуск Gradio UI
CMD ["python", "gradio_ui.py"]
