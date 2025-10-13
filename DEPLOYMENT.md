# 🚀 Инструкция по развертыванию на новой виртуальной машине

## Предварительные требования

### Системные требования
- **ОС**: Linux (Ubuntu 20.04/22.04), Windows Server 2019+, или macOS
- **RAM**: Минимум 4GB, рекомендуется 8GB+
- **Диск**: Минимум 10GB свободного места
- **CPU**: 2+ ядра

### Необходимое ПО
1. **Docker** версии 20.10+
2. **Docker Compose** версии 1.29+
3. **Git** (для клонирования репозитория)

---

## Шаг 1: Установка Docker и Docker Compose

### Ubuntu/Debian

```bash
# Обновить систему
sudo apt-get update
sudo apt-get upgrade -y

# Установить зависимости
sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common

# Добавить Docker GPG ключ
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Добавить Docker репозиторий
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Установить Docker
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Проверить установку
docker --version
docker compose version
```

### CentOS/RHEL

```bash
# Установить зависимости
sudo yum install -y yum-utils
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

# Установить Docker
sudo yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Запустить Docker
sudo systemctl start docker
sudo systemctl enable docker

# Проверить установку
docker --version
docker compose version
```

### Windows Server

1. Установить Docker Desktop для Windows: https://docs.docker.com/desktop/install/windows-install/
2. Включить WSL2 (Windows Subsystem for Linux)
3. Перезагрузить систему

---

## Шаг 2: Клонирование репозитория

```bash
# Клонировать репозиторий
git clone <REPOSITORY_URL>
cd doc-analysis-service

# Или скачать ZIP и распаковать
```

---

## Шаг 3: Настройка переменных окружения

### 3.1 Настройка API ключа OpenAI

```bash
# Перейти в папку api-service
cd api-service

# Скопировать шаблон
cp .env.example .env

# Отредактировать файл
nano .env  # или vim, или любой текстовый редактор
```

**Содержимое `api-service/.env`:**

```env
# Получить ключ: https://platform.openai.com/api-keys
OPENAI_API_KEY=sk-proj-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

# Опционально: выбрать модель (по умолчанию gpt-5-mini из config.py)
# OPENAI_MODEL=gpt-5-mini
```

### 3.2 (Опционально) Настройка прокси

Если OpenAI API недоступен напрямую (блокировки, корпоративная сеть):

```bash
# Вернуться в корень проекта
cd ..

# Создать .env для docker-compose
nano .env
```

**Содержимое `.env` в корне:**

```env
# Для SOCKS5 прокси
HTTPS_PROXY=socks5://127.0.0.1:10808
HTTP_PROXY=socks5://127.0.0.1:10808

# Или для HTTP/HTTPS прокси
# HTTPS_PROXY=http://proxy-server:3128
# HTTP_PROXY=http://proxy-server:3128
```

**Раскомментировать в `docker-compose.yml`:**

```yaml
environment:
  # Раскомментировать эти строки:
  - HTTPS_PROXY=${HTTPS_PROXY:-}
  - HTTP_PROXY=${HTTP_PROXY:-}
```

---

## Шаг 4: Сборка и запуск

```bash
# Убедиться что вы в корне проекта
cd /path/to/doc-analysis-service

# Собрать и запустить контейнеры
docker compose up --build -d

# Первая сборка займет 3-5 минут
```

### Проверка статуса

```bash
# Проверить запущенные контейнеры
docker compose ps

# Должны быть запущены:
# doc_analysis_api       (api-service)
# doc_analysis_ui_react  (ui-react-service)

# Просмотр логов
docker compose logs -f

# Просмотр логов конкретного сервиса
docker compose logs -f doc_analysis_api
docker compose logs -f doc_analysis_ui_react
```

---

## Шаг 5: Проверка работоспособности

### 5.1 Проверка API

```bash
# Проверка healthcheck
curl http://localhost:8002/

# Ожидаемый ответ:
# {
#   "status": "ok",
#   "service": "Document Analysis API (VISION MODE)",
#   "model": "gpt-5-mini",
#   ...
# }
```

### 5.2 Проверка UI

Откройте браузер и перейдите на:

```
http://localhost:7862
```

Вы должны увидеть интерфейс приложения.

---

## Шаг 6: Настройка firewall (опционально)

Если сервис должен быть доступен извне:

### Ubuntu/Debian (ufw)

```bash
# Открыть порт 7862 для UI
sudo ufw allow 7862/tcp

# Опционально: открыть порт 8002 для прямого доступа к API
# sudo ufw allow 8002/tcp

# Проверить статус
sudo ufw status
```

### CentOS/RHEL (firewalld)

```bash
# Открыть порт 7862
sudo firewall-cmd --permanent --add-port=7862/tcp
sudo firewall-cmd --reload

# Проверить
sudo firewall-cmd --list-ports
```

---

## Шаг 7: Настройка автозапуска

Docker Compose контейнеры настроены с `restart: unless-stopped`, поэтому они автоматически запустятся при перезагрузке системы.

Убедитесь что Docker запускается автоматически:

```bash
# Включить автозапуск Docker
sudo systemctl enable docker

# Проверить
sudo systemctl is-enabled docker
```

---

## Обновление приложения

```bash
# Остановить контейнеры
docker compose down

# Получить последние изменения
git pull

# Пересобрать и запустить
docker compose up --build -d
```

---

## Остановка и удаление

```bash
# Остановить контейнеры (данные сохраняются)
docker compose stop

# Остановить и удалить контейнеры (данные сохраняются)
docker compose down

# Удалить контейнеры и volumes (УДАЛИТ ВСЕ ДАННЫЕ)
docker compose down -v

# Удалить образы
docker compose down --rmi all
```

---

## Troubleshooting

### Проблема: Контейнер api-service не запускается

```bash
# Проверить логи
docker compose logs doc_analysis_api

# Частые причины:
# 1. Отсутствует .env файл или OPENAI_API_KEY
# 2. Неверный формат API ключа
# 3. Порт 8002 уже занят
```

**Решение:**
```bash
# Проверить .env
cat api-service/.env

# Проверить занятые порты
sudo netstat -tlnp | grep 8002
```

### Проблема: Ошибка "cannot connect to OpenAI API"

```bash
# Проверить интернет-соединение
curl https://api.openai.com

# Если нужен прокси - настроить по инструкции выше
```

### Проблема: UI не загружается

```bash
# Проверить статус контейнера
docker compose ps

# Проверить логи nginx
docker compose logs doc_analysis_ui_react

# Пересобрать UI
docker compose up --build doc_analysis_ui_react
```

### Проблема: "Rate limit exceeded"

OpenAI API имеет лимиты. Решение:
1. Подождать несколько минут
2. Уменьшить параметры в `api-service/config.py`
3. Обновить тарифный план OpenAI

---

## Мониторинг

### Использование ресурсов

```bash
# Просмотр использования ресурсов контейнерами
docker stats

# Просмотр использования диска
docker system df
```

### Healthcheck

```bash
# Проверка здоровья API
curl http://localhost:8002/status

# Проверка здоровья контейнера
docker inspect --format='{{.State.Health.Status}}' doc_analysis_api
```

---

## Безопасность

### Рекомендации:

1. **Защита API ключей**:
   - Никогда не коммитить `.env` файлы в Git
   - Ограничить доступ к файлам: `chmod 600 api-service/.env`

2. **Firewall**:
   - Открыть только необходимые порты
   - Использовать reverse proxy (nginx/traefik) для SSL

3. **Обновления**:
   - Регулярно обновлять Docker образы
   - Мониторить CVE в зависимостях

4. **Логи**:
   - Настроить ротацию логов
   - Не логировать чувствительные данные

---

## Производственное развертывание (Production)

Для production окружения рекомендуется:

1. **Reverse Proxy с SSL**:
   ```yaml
   # Добавить nginx-proxy или traefik
   # Настроить Let's Encrypt для SSL
   ```

2. **Мониторинг**:
   - Prometheus + Grafana
   - ELK Stack для логов

3. **Backup**:
   - Регулярный backup volumes
   - Backup базы данных (если добавите)

4. **Масштабирование**:
   ```bash
   # Запустить несколько реплик API
   docker compose up --scale doc-analysis-api=3
   ```

---

## Контакты и поддержка

При возникновении проблем:
1. Проверьте логи: `docker compose logs -f`
2. Просмотрите [README.md](README.md)
3. Создайте issue в репозитории с описанием проблемы и логами
