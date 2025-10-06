"""
Gradio веб-интерфейс для анализа проектной документации
Работает в корпоративной сети БЕЗ прокси
Обращается к API-сервису для анализа через Google Gemini
"""
import os
import json
import gradio as gr
import requests
from typing import Optional, Tuple
from pathlib import Path
from dotenv import load_dotenv


# ============================
# КОНФИГУРАЦИЯ
# ============================

load_dotenv()

# URL API-сервиса (можно задать через переменную окружения)
API_SERVICE_URL = os.getenv("API_SERVICE_URL", "http://doc-analysis-api:8000")

# Словарь примеров имен для валидации файлов
VALIDATION_EXAMPLES = {
    "technical_assignment": [
        "tz_project.docx", "tech_assignment.pdf", "tz_rd.docx",
        "tz_", "техническое_задание", "тз_"
    ],
    "documentation": [
        "documentation_fe.pdf", "docs_project.docx", "fe_docs.pdf",
        "documentation_", "docs_", "проектная_документация"
    ],
    "technical_requirements": [
        "_tu.docx", "_tu.pdf", "tech_requirements_",
        "технические_условия", "ту_"
    ]
}

# Стадии документации
STAGES = {
    "ГК": "Градостроительная концепция",
    "ФЭ": "Форэскизный проект",
    "ЭП": "Эскизный проект",
    "ПД": "Проектная документация (стадия П)",
    "РД": "Рабочая документация"
}

# Типы требований
REQUIREMENT_TYPES = {
    "ТЗ": "ТЗ на проектирование (общие требования)",
    "ТУ_РД": "ТУ на проектирование для РД",
    "ТУ_ПД": "ТУ на проектирование для ПД",
    "ТУ_ФЭ": "ТУ на проектирование для ФЭ",
    "ТУ_ЭП": "ТУ на проектирование для ЭП"
}

# Допустимые форматы файлов
ALLOWED_FORMATS = [".docx", ".pdf"]


# ============================
# ФУНКЦИИ ВАЛИДАЦИИ
# ============================

def validate_file_format(filename: str) -> Tuple[bool, str]:
    """Валидация формата файла"""
    if not filename:
        return False, "Файл не загружен"

    file_ext = Path(filename).suffix.lower()
    if file_ext not in ALLOWED_FORMATS:
        return False, f"Неподдерживаемый формат файла. Разрешены только: {', '.join(ALLOWED_FORMATS)}"

    return True, ""


def validate_file_by_name(filename: str, file_type: str) -> Tuple[bool, str]:
    """Валидация файла по имени на основе словаря примеров"""
    if not filename:
        return False, "Файл не загружен"

    # Проверка формата
    format_valid, format_error = validate_file_format(filename)
    if not format_valid:
        return False, format_error

    # Получаем имя без расширения и приводим к нижнему регистру
    file_basename = Path(filename).stem.lower()

    # Получаем список паттернов для данного типа
    patterns = VALIDATION_EXAMPLES.get(file_type, [])

    # Проверяем, содержит ли имя файла хотя бы один из паттернов
    matches = any(pattern.lower() in file_basename for pattern in patterns)

    if not matches:
        examples = ", ".join(VALIDATION_EXAMPLES[file_type][:3])
        return False, f"Имя файла не соответствует типу '{file_type}'. Примеры корректных имён: {examples}"

    return True, ""


def validate_all_inputs(
    tz_file,
    doc_file,
    stage: str,
    req_type: str,
    tu_file=None
) -> Tuple[bool, str]:
    """Комплексная валидация всех входных данных"""
    # Валидация ТЗ
    if tz_file is None:
        return False, json.dumps({"error": "Не загружен файл технического задания"}, ensure_ascii=False)

    valid, error = validate_file_by_name(tz_file.name, "technical_assignment")
    if not valid:
        return False, json.dumps({"error": f"Техническое задание: {error}"}, ensure_ascii=False)

    # Валидация документации
    if doc_file is None:
        return False, json.dumps({"error": "Не загружен файл документации"}, ensure_ascii=False)

    valid, error = validate_file_by_name(doc_file.name, "documentation")
    if not valid:
        return False, json.dumps({"error": f"Документация: {error}"}, ensure_ascii=False)

    # Валидация ТУ для РД и ПД
    if req_type in ["ТУ_РД", "ТУ_ПД"]:
        if tu_file is None:
            return False, json.dumps({"error": f"Для типа требований '{REQUIREMENT_TYPES[req_type]}' необходимо загрузить файл технических условий"}, ensure_ascii=False)

        valid, error = validate_file_by_name(tu_file.name, "technical_requirements")
        if not valid:
            return False, json.dumps({"error": f"Технические условия: {error}"}, ensure_ascii=False)

    return True, ""


# ============================
# ОБРАБОТКА ФАЙЛОВ
# ============================

def extract_file_content(file_path: str) -> str:
    """
    Извлечение содержимого из файла

    В реальной системе здесь должна быть интеграция с библиотеками:
    - python-docx для DOCX
    - PyPDF2 или pdfplumber для PDF
    - OCR для изображений в PDF

    Сейчас возвращаем заглушку
    """
    filename = Path(file_path).name
    file_ext = Path(file_path).suffix.lower()

    # ЗАГЛУШКА: В реальной системе здесь парсинг файла
    return f"[Содержимое файла {filename} ({file_ext}) - заглушка для демонстрации]"


# ============================
# ВЗАИМОДЕЙСТВИЕ С API
# ============================

def call_analysis_api(
    stage: str,
    req_type: str,
    tz_file_path: str,
    doc_file_path: str,
    tu_file_path: Optional[str] = None
) -> dict:
    """
    Вызов API-сервиса для анализа документации

    Args:
        stage: стадия документации
        req_type: тип требований
        tz_file_path: путь к файлу ТЗ
        doc_file_path: путь к файлу документации
        tu_file_path: путь к файлу ТУ (опционально)

    Returns:
        dict: результат анализа от API
    """
    try:
        # Извлечение содержимого файлов
        tz_content = extract_file_content(tz_file_path)
        doc_content = extract_file_content(doc_file_path)

        # Формирование запроса к API
        payload = {
            "stage": stage,
            "req_type": req_type,
            "tz_document": {
                "filename": Path(tz_file_path).name,
                "content_summary": tz_content
            },
            "doc_document": {
                "filename": Path(doc_file_path).name,
                "content_summary": doc_content
            }
        }

        # Добавление ТУ если есть
        if tu_file_path:
            tu_content = extract_file_content(tu_file_path)
            payload["tu_document"] = {
                "filename": Path(tu_file_path).name,
                "content_summary": tu_content
            }

        # Отправка запроса к API
        print(f"📡 Отправка запроса к API: {API_SERVICE_URL}/analyze")
        response = requests.post(
            f"{API_SERVICE_URL}/analyze",
            json=payload,
            timeout=300  # 5 минут таймаут для анализа
        )

        response.raise_for_status()
        return response.json()

    except requests.exceptions.ConnectionError:
        return {
            "error": f"Не удалось подключиться к API-сервису по адресу {API_SERVICE_URL}. Проверьте, что сервис запущен."
        }
    except requests.exceptions.Timeout:
        return {
            "error": "Превышено время ожидания ответа от API-сервиса (5 минут)"
        }
    except requests.exceptions.HTTPError as e:
        return {
            "error": f"Ошибка HTTP от API-сервиса: {e.response.status_code} - {e.response.text}"
        }
    except Exception as e:
        return {
            "error": f"Неожиданная ошибка при обращении к API: {str(e)}"
        }


# ============================
# ФОРМАТИРОВАНИЕ РЕЗУЛЬТАТОВ
# ============================

def format_analysis_results(api_response: dict) -> str:
    """
    Форматирование результатов анализа в Markdown

    Args:
        api_response: ответ от API-сервиса

    Returns:
        str: форматированный Markdown
    """
    # Проверка на ошибку
    if "error" in api_response:
        return f"""
## ❌ Ошибка

{api_response['error']}
"""

    # Извлечение данных
    stage = api_response.get("stage", "")
    req_type = api_response.get("req_type", "")
    requirements = api_response.get("requirements", [])
    summary = api_response.get("summary", "")

    # Формирование таблицы
    table_rows = []
    for req in requirements:
        row = f"""| {req.get('number', '-')} | {req.get('requirement', '-')} | {req.get('status', '-')} | {req.get('confidence', 0)} | {req.get('solution_description', '-')} | {req.get('reference', '-')} | {req.get('discrepancies', '-')} | {req.get('recommendations', '-')} |"""
        table_rows.append(row)

    table = "\n".join(table_rows) if table_rows else "| - | Требования не найдены | - | - | - | - | - | - |"

    result = f"""
## ✅ Результаты анализа документации

**Стадия:** {STAGES.get(stage, stage)}
**Тип требований:** {REQUIREMENT_TYPES.get(req_type, req_type)}

---

### 📊 Таблица анализа требований

| № | Требование из ТЗ | Статус исполнения | Достоверность (%) | Описание решения | Ссылка (документ, лист/страница) | Выявленные несоответствия и комментарии | Рекомендации |
|---|------------------|-------------------|-------------------|------------------|----------------------------------|----------------------------------------|--------------|
{table}

---

### 📝 Общая сводка

{summary}

---

**Всего проанализировано требований:** {len(requirements)}
**Источник:** Google Gemini API
"""

    return result


# ============================
# ОСНОВНАЯ ЛОГИКА ОБРАБОТКИ
# ============================

def process_documentation_analysis(
    tz_file,
    doc_file,
    stage: str,
    req_type: str,
    tu_file=None
) -> str:
    """
    Основная функция обработки и анализа документации

    Args:
        tz_file: файл технического задания
        doc_file: файл проектной документации
        stage: стадия документации
        req_type: тип требований
        tu_file: файл технических условий (опционально)

    Returns:
        str: результат в формате Markdown или JSON с ошибкой
    """
    print(f"🔍 Начало анализа: стадия={stage}, тип={req_type}")

    # Валидация входных данных
    valid, error_msg = validate_all_inputs(tz_file, doc_file, stage, req_type, tu_file)
    if not valid:
        return f"## ❌ Ошибка валидации\n\n```json\n{error_msg}\n```"

    print("✅ Валидация прошла успешно")

    # Вызов API для анализа
    print(f"📡 Обращение к API-сервису: {API_SERVICE_URL}")
    api_response = call_analysis_api(
        stage=stage,
        req_type=req_type,
        tz_file_path=tz_file.name,
        doc_file_path=doc_file.name,
        tu_file_path=tu_file.name if tu_file else None
    )

    # Форматирование результатов
    result = format_analysis_results(api_response)

    print("✅ Анализ завершен")
    return result


def update_tu_visibility(req_type: str):
    """Обновление видимости поля загрузки ТУ"""
    if req_type in ["ТУ_РД", "ТУ_ПД"]:
        return gr.update(visible=True)
    else:
        return gr.update(visible=False)


# ============================
# GRADIO ИНТЕРФЕЙС
# ============================

def create_interface():
    """Создание Gradio интерфейса"""

    with gr.Blocks(title="Анализ проектной документации", theme=gr.themes.Soft()) as interface:
        gr.Markdown("""
        # 📋 Анализ соответствия проектной документации техническому заданию

        Система автоматического анализа проектной документации на соответствие требованиям ТЗ/ТУ
        **Анализ выполняется через Google Gemini API**
        """)

        with gr.Row():
            # Левая колонка - загрузка файлов
            with gr.Column(scale=1):
                gr.Markdown("### 📁 Загрузка файлов")

                tz_file = gr.File(
                    label="Техническое задание (ТЗ)",
                    file_types=[".docx", ".pdf"],
                    type="filepath"
                )
                gr.Markdown("*Принимаются файлы: .docx, .pdf*")

                doc_file = gr.File(
                    label="Проектная документация",
                    file_types=[".docx", ".pdf"],
                    type="filepath"
                )
                gr.Markdown("*Принимаются файлы: .docx, .pdf*")

                tu_file = gr.File(
                    label="Технические условия (ТУ)",
                    file_types=[".docx", ".pdf"],
                    type="filepath",
                    visible=False
                )
                gr.Markdown("*Загружается для стадий РД и ПД*")

            # Правая колонка - параметры анализа
            with gr.Column(scale=1):
                gr.Markdown("### ⚙️ Параметры анализа")

                stage = gr.Radio(
                    choices=list(STAGES.keys()),
                    label="Стадия документации",
                    value="ФЭ",
                    info="Выберите стадию разработки проектной документации"
                )

                req_type = gr.Radio(
                    choices=list(REQUIREMENT_TYPES.keys()),
                    label="Тип требований",
                    value="ТЗ",
                    info="Выберите тип требований для анализа"
                )

                # Информационный блок
                gr.Markdown(f"""
                **ℹ️ Справка:**
                - **ГК** - Градостроительная концепция
                - **ФЭ** - Форэскизный проект (встроенные ТУ)
                - **ЭП** - Эскизный проект (встроенные ТУ)
                - **ПД** - Проектная документация (требуется загрузка ТУ)
                - **РД** - Рабочая документация (требуется загрузка ТУ)

                **API сервис:** `{API_SERVICE_URL}`
                """)

        # Кнопка запуска анализа
        analyze_btn = gr.Button("🔍 Выполнить анализ через Gemini API", variant="primary", size="lg")

        # Область вывода результатов
        gr.Markdown("### 📊 Результаты анализа")
        output = gr.Markdown()

        # Связывание событий
        req_type.change(
            fn=update_tu_visibility,
            inputs=[req_type],
            outputs=[tu_file]
        )

        analyze_btn.click(
            fn=process_documentation_analysis,
            inputs=[tz_file, doc_file, stage, req_type, tu_file],
            outputs=[output]
        )

        # Примеры использования
        gr.Markdown("""
        ---
        ### 📚 Примеры корректных имён файлов

        **Техническое задание:**
        - `tz_project.docx`, `tech_assignment.pdf`, `tz_rd.docx`

        **Документация:**
        - `documentation_fe.pdf`, `docs_project.docx`, `fe_docs.pdf`

        **Технические условия:**
        - `requirements_tu.docx`, `project_tu.pdf` (суффикс `_tu`)

        *Словарь примеров для валидации: [naming-conventions](https://example.com/naming-conventions)*
        """)

    return interface


# ============================
# ЗАПУСК ПРИЛОЖЕНИЯ
# ============================

if __name__ == "__main__":
    print("🚀 Запуск Gradio UI для анализа проектной документации...")
    print(f"📡 API сервис: {API_SERVICE_URL}")

    interface = create_interface()

    # Запуск на всех интерфейсах (доступен из корпоративной сети)
    interface.launch(
        server_name="0.0.0.0",
        server_port=7861,
        share=False
    )
