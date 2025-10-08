"""
Gradio веб-интерфейс для анализа проектной документации.
Обращается к API-сервису для выполнения анализа.
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

API_SERVICE_URL = os.getenv("API_SERVICE_URL", "http://doc-analysis-api:8000")

STAGES = {
    "ГК": "Градостроительная концепция",
    "ФЭ": "Форэскизный проект",
    "ЭП": "Эскизный проект"
}

# Добавлен ТЗ для общего анализа
REQUIREMENT_TYPES = {
    "ТЗ": "ТЗ на проектирование (общие требования)",
    "ТУ_ФЭ": "ТУ на проектирование для ФЭ",
    "ТУ_ЭП": "ТУ на проектирование для ЭП"
}

ALLOWED_FORMATS = [".docx", ".pdf"]

# ============================ 
# ВАЛИДАЦИЯ (остается на клиенте для быстрой обратной связи)
# ============================ 

def validate_all_inputs(
    tz_file,
    doc_file,
    stage: str,
    check_tu: bool,
    tu_file=None
) -> Tuple[bool, str]:
    """Комплексная валидация всех входных данных."""
    if tz_file is None:
        return False, json.dumps({"error": "Не загружен файл технического задания"}, ensure_ascii=False)
    
    if doc_file is None:
        return False, json.dumps({"error": "Не загружен файл документации"}, ensure_ascii=False)

    if check_tu:
        if stage not in ["ФЭ", "ЭП"] and tu_file is None:
            return False, json.dumps({"error": "Для выбранной стадии требуется загрузить файл ТУ или отключить опцию проверки ТУ"}, ensure_ascii=False)

    return True, ""

# ============================ 
# ВЗАИМОДЕЙСТВИЕ С API
# ============================ 

def call_analysis_api(
    stage: str,
    check_tu: bool,
    tz_file_path: str,
    doc_file_path: str,
    tu_file_path: Optional[str] = None
) -> dict:
    """
    Вызов API-сервиса для анализа документации путем отправки файлов.
    """
    session = requests.Session()

    try:
        # Открываем файлы с context manager для автоматического закрытия
        with open(tz_file_path, 'rb') as tz_f, open(doc_file_path, 'rb') as doc_f:
            files_to_send = {
                'tz_document': (Path(tz_file_path).name, tz_f, 'application/octet-stream'),
                'doc_document': (Path(doc_file_path).name, doc_f, 'application/octet-stream')
            }

            data_to_send = {
                "stage": stage,
                "check_tu": str(check_tu).lower(),
                "req_type": "ТЗ"
            }

            # Если есть ТУ файл (для стадий, где он обязателен), прикрепляем
            if tu_file_path:
                with open(tu_file_path, 'rb') as tu_f:
                    files_to_send['tu_document'] = (Path(tu_file_path).name, tu_f, 'application/octet-stream')

                    print(f"📡 Отправка запроса с файлами к API: {API_SERVICE_URL}/analyze")
                    response = session.post(
                        f"{API_SERVICE_URL}/analyze",
                        files=files_to_send,
                        data=data_to_send,
                        timeout=2400  # 40 минут для больших проектов (100+ страниц, 30+ требований)
                    )
                    response.raise_for_status()
                    return response.json()

            print(f"📡 Отправка запроса с файлами к API: {API_SERVICE_URL}/analyze")
            response = session.post(
                f"{API_SERVICE_URL}/analyze",
                files=files_to_send,
                data=data_to_send,
                timeout=2400  # 40 минут для больших проектов (100+ страниц, 30+ требований)
            )
            response.raise_for_status()
            return response.json()

    except requests.exceptions.ConnectionError:
        return {
            "error": f"Не удалось подключиться к API-сервису по адресу {API_SERVICE_URL}. Проверьте, что сервис запущен."
        }
    except requests.exceptions.Timeout:
        return {
            "error": "Превышено время ожидания ответа от API-сервиса (40 минут). Попробуйте уменьшить размер документа, отключить Stage 4 (поиск противоречий) в config.py или обратитесь к администратору."
        }
    except requests.exceptions.HTTPError as e:
        # Пытаемся извлечь detail из JSON-ответа, если возможно
        try:
            detail = e.response.json().get('detail', e.response.text)
        except json.JSONDecodeError:
            detail = e.response.text
        return {
            "error": f"Ошибка HTTP от API-сервиса: {e.response.status_code} - {detail}"
        }
    except Exception as e:
        return {
            "error": f"Неожиданная ошибка при обращении к API: {str(e)}"
        }
    finally:
        # Закрываем сессию для освобождения ресурсов
        session.close()

# ============================ 
# ФОРМАТИРОВАНИЕ РЕЗУЛЬТАТОВ
# ============================ 

def format_analysis_results(api_response: dict) -> str:
    """Форматирование результатов анализа в Markdown."""
    if "error" in api_response:
        return f"## ❌ Ошибка\n\n```\n{api_response['error']}\n```"

    stage = api_response.get("stage", "")
    req_type = api_response.get("req_type", "")
    requirements = api_response.get("requirements", [])
    summary = api_response.get("summary", "")

    table_rows = []
    for req in requirements:
        row = f"| {req.get('number', '-')} | {req.get('requirement', '-')} | {req.get('status', '-')} | {req.get('confidence', 0)} | {req.get('solution_description', '-')} | {req.get('reference', '-')} | {req.get('discrepancies', '-')} | {req.get('recommendations', '-')} |"
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
"""

    return result

# ============================ 
# ОСНОВНАЯ ЛОГИКА ОБРАБОТКИ
# ============================ 

def process_documentation_analysis(
    tz_file,
    doc_file,
    stage: str,
    check_tu: bool,
    tu_file=None
) -> str:
    """Основная функция обработки и анализа документации."""
    print("🔍 Начало анализа...")

    valid, error_msg = validate_all_inputs(tz_file, doc_file, stage, check_tu, tu_file)
    if not valid:
        return f"## ❌ Ошибка валидации\n\n```json\n{error_msg}\n```"

    print("✅ Валидация пройдена. Обращение к API-сервису...")

    # Gradio File object имеет атрибут .name с путем к временному файлу
    api_response = call_analysis_api(
        stage=stage,
        check_tu=check_tu,
        tz_file_path=tz_file.name,
        doc_file_path=doc_file.name,
        tu_file_path=tu_file.name if tu_file else None
    )

    print("📊 Получен ответ от API. Форматирование результата...")

    result = format_analysis_results(api_response)

    print("✅ Анализ завершен!")
    return result

def update_tu_visibility(stage: str, check_tu: bool):
    """Обновление видимости поля загрузки ТУ: требуется только если включена проверка ТУ и стадия не ФЭ/ЭП."""
    needs_tu_upload = bool(check_tu and stage not in ["ФЭ", "ЭП"])  # ПД/РД удалены
    return gr.update(visible=needs_tu_upload)

# ============================ 
# GRADIO ИНТЕРФЕЙС
# ============================ 

def create_interface():
    """Создание Gradio интерфейса."""
    with gr.Blocks(title="Анализ проектной документации", theme=gr.themes.Soft()) as interface:
        gr.Markdown("""
        # 📋 Анализ соответствия проектной документации
        Система автоматического анализа на соответствие требованиям ТЗ/ТУ с использованием AI.

        ⚠️ **ВАЖНО:** Не закрывайте эту вкладку во время анализа! При закрытии вкладки анализ будет прерван,
        прогресс потеряется, и потребуется запускать анализ заново.
        """)

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 📁 Загрузка файлов")
                tz_file = gr.File(label="Техническое задание (ТЗ)", file_types=ALLOWED_FORMATS)
                doc_file = gr.File(label="Проектная документация", file_types=ALLOWED_FORMATS)
                tu_file = gr.File(label="Технические условия (ТУ)", file_types=ALLOWED_FORMATS, visible=False)

            with gr.Column(scale=1):
                gr.Markdown("### ⚙️ Параметры анализа")
                stage = gr.Radio(choices=list(STAGES.keys()), label="Стадия документации", value="ФЭ")
                check_tu = gr.Checkbox(label="Добавить проверку ТУ", value=False)
                gr.Markdown(f"**API сервис:** `{API_SERVICE_URL}`")

        analyze_btn = gr.Button("🔍 Выполнить анализ", variant="primary", size="lg")
        
        status = gr.Textbox(label="Статус", interactive=False, visible=False)
        output = gr.Markdown(label="Результаты анализа")

        # Связывание событий
        stage.change(fn=update_tu_visibility, inputs=[stage, check_tu], outputs=[tu_file])
        check_tu.change(fn=update_tu_visibility, inputs=[stage, check_tu], outputs=[tu_file])

        analyze_btn.click(
            fn=process_documentation_analysis,
            inputs=[tz_file, doc_file, stage, check_tu, tu_file],
            outputs=[output]
        )

    return interface

# ============================ 
# ЗАПУСК ПРИЛОЖЕНИЯ
# ============================ 

if __name__ == "__main__":
    print("🚀 Запуск Gradio UI для анализа проектной документации...")
    print(f"📡 API сервис: {API_SERVICE_URL}")
    interface = create_interface()
    interface.launch(server_name="0.0.0.0", server_port=7861, share=False)