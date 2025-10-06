"""
FastAPI сервис для анализа документации с использованием Google Gemini API.
Использует нативный File API для обработки документов до 2GB.
"""
import os
import json
import logging
import asyncio
import tempfile
from typing import List, Optional, Dict, Any

import uvicorn
from fastapi import FastAPI, HTTPException, Form, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai
from dotenv import load_dotenv

# ============================
# КОНФИГУРАЦИЯ
# ============================

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Инициализация Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logger.error("GEMINI_API_KEY не установлен в переменных окружения!")
    raise ValueError("GEMINI_API_KEY is required")

genai.configure(api_key=GEMINI_API_KEY)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.1"))

logger.info(f"Используется Google Gemini: {GEMINI_MODEL}")


# ============================
# СИСТЕМА ПРОМПТОВ
# ============================

PROMPTS = {
    "ГК": """<анализ_документации_гк>
<задача>
Провести комплексный анализ соответствия проектной документации стадии Градостроительная концепция (ГК)
требованиям технического задания с проверкой концептуальных и планировочных решений.
</задача>
<критерии_оценки>
- Полностью исполнено: требование реализовано в полном объёме согласно ТЗ
- Частично исполнено: реализовано не полностью или с отклонениями
- Не исполнено: не отражено в проектных решениях
- Требует уточнения: недостаточно данных для однозначной оценки
</критерии_оценки>
</анализ_документации_гк>""",
    "ФЭ": """<анализ_документации_фэ>
<задача>
Провести комплексный анализ соответствия проектной документации стадии Форэскиз (ФЭ) требованиям технического задания с детальной проверкой графических и текстовых материалов.
</задача>
<исходные_данные>
1. Проектная документация стадии ФЭ в формате PDF/DOCX, включающая:
  - Графическую часть (планы, разрезы, фасады, схемы)
  - Текстовую часть (пояснительная записка, спецификации, ведомости)
2. Техническое задание на разработку проектной документации стадии ФЭ
</исходные_данные>
<методика_анализа>
Для каждого требования ТЗ:
1. Определить его тип (архитектурно-планировочное, конструктивное, инженерное, экономическое)
2. Найти соответствующие проектные решения в документации
3. Оценить полноту и корректность исполнения
4. Выявить отклонения или неточности
</методика_анализа>
<критерии_оценки>
- Полностью исполнено: требование реализовано в полном объёме согласно ТЗ
- Частично исполнено: реализовано не полностью или с отклонениями
- Не исполнено: не отражено в проектных решениях
- Требует уточнения: недостаточно данных для однозначной оценки
</критерии_оценки>
<дополнительные_указания>
- При анализе графических материалов обращать внимание на масштабы, размеры, обозначения
- В текстовой части проверять соответствие технико-экономических показателей
- Фиксировать противоречия между разными разделами документации
- Отмечать отсутствие обязательных для стадии ФЭ материалов
</дополнительные_указания>
</анализ_документации_фэ>""",
    "ЭП": """<анализ_документации_эп>
<задача>
Провести комплексный анализ соответствия проектной документации стадии Эскизный проект (ЭП)
требованиям технического задания с детальной проверкой архитектурных и объемно-планировочных решений.
</задача>
<критерии_оценки>
- Полностью исполнено: требование реализовано в полном объёме согласно ТЗ
- Частично исполнено: реализовано не полностью или с отклонениями
- Не исполнено: не отражено в проектных решениях
- Требует уточнения: недостаточно данных для однозначной оценки
</критерии_оценки>
</анализ_документации_эп>""",
    "ПД": """<анализ_документации_пд>
<задача>
Провести комплексный анализ соответствия проектной документации стадии Проектная документация (ПД)
требованиям технического задания и технических условий с проверкой всех разделов и инженерных систем.
</задача>
<критерии_оценки>
- Полностью исполнено: требование реализовано в полном объёме согласно ТЗ/ТУ
- Частично исполнено: реализовано не полностью или с отклонениями
- Не исполнено: не отражено в проектных решениях
- Требует уточнения: недостаточно данных для однозначной оценки
</критерии_оценки>
<дополнительные_указания>
- Проверять соответствие нормам и стандартам
- Контролировать полноту состава проектной документации
- Проверять согласованность между разделами
</дополнительные_указания>
</анализ_документации_пд>""",
    "РД": """<анализ_документации_рд>
<задача>
Провести комплексный анализ соответствия рабочей документации (РД) требованиям технического задания
и технических условий с проверкой детализации решений для строительства.
</задача>
<критерии_оценки>
- Полностью исполнено: требование реализовано в полном объёме согласно ТЗ/ТУ
- Частично исполнено: реализовано не полностью или с отклонениями
- Не исполнено: не отражено в проектных решениях
- Требует уточнения: недостаточно данных для однозначной оценки
</критерии_оценки>
<дополнительные_указания>
- Проверять достаточную детализацию для производства работ
- Контролировать наличие рабочих чертежей и спецификаций
- Проверять соответствие ПД и РД
</дополнительные_указания>
</анализ_документации_рд>"""
}

# ============================
# PYDANTIC МОДЕЛИ
# ============================

class RequirementAnalysis(BaseModel):
    """Результат анализа одного требования"""
    number: int
    requirement: str
    status: str
    confidence: int
    solution_description: str
    reference: str
    discrepancies: str
    recommendations: str

class AnalysisResponse(BaseModel):
    """Ответ с результатами анализа"""
    stage: str
    req_type: str
    requirements: List[RequirementAnalysis]
    summary: str

# ============================
# FASTAPI ПРИЛОЖЕНИЕ
# ============================

app = FastAPI(
    title="Document Analysis API",
    description="API для анализа проектной документации с использованием Google Gemini",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================
# API ENDPOINTS
# ============================

@app.get("/")
async def root():
    """Health check"""
    return {
        "status": "ok",
        "service": "Document Analysis API",
        "provider": "gemini",
        "model": GEMINI_MODEL
    }

@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_documentation(
    stage: str = Form(...),
    req_type: str = Form(...),
    tz_document: UploadFile = File(...),
    doc_document: UploadFile = File(...),
    tu_document: Optional[UploadFile] = File(None)
):
    """
    Основной endpoint для анализа документации.
    Принимает файлы и метаданные в multipart/form-data.
    """
    try:
        logger.info(f"Получен запрос на анализ. Стадия: {stage}, Тип: {req_type}")

        # Загрузка файлов в Gemini File API
        logger.info("Загрузка файлов в Gemini File API...")
        uploaded_files = await _upload_files_to_gemini_api([tz_document, doc_document, tu_document])

        # Построение промпта
        prompt = _build_multimodal_prompt(stage, req_type, uploaded_files)

        # Отправка запроса в Gemini API
        logger.info("Отправка запроса в Google Gemini API с файлами...")
        analysis_result_text = await _call_gemini_api(prompt)

        # Парсинг результата
        logger.info("Парсинг результатов анализа...")
        parsed_result = _parse_analysis_response(analysis_result_text, stage, req_type)

        logger.info("Анализ завершен успешно")
        return parsed_result

    except Exception as e:
        logger.error(f"Ошибка при анализе документации: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка анализа: {str(e)}")

# ============================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================

async def _upload_files_to_gemini_api(files: List[Optional[UploadFile]]) -> Dict[str, Any]:
    """Асинхронно загружает файлы в Gemini File API."""

    async def upload(file: UploadFile):
        logger.info(f"Загружается файл: {file.filename}")
        file_bytes = await file.read()

        # Gemini API требует путь к файлу, создаем временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            # genai.upload_file не является async, запускаем в executor'е
            loop = asyncio.get_running_loop()
            uploaded_file = await loop.run_in_executor(
                None,
                lambda: genai.upload_file(path=tmp_path, display_name=file.filename)
            )
            logger.info(f"Файл {uploaded_file.name} ({uploaded_file.display_name}) успешно загружен.")
            return file.filename, uploaded_file
        finally:
            # Удаляем временный файл
            os.unlink(tmp_path)

    # Определяем, какой файл какому ключу соответствует
    file_map = {
        files[0].filename: "tz_document",
        files[1].filename: "doc_document",
    }
    if files[2]:
        file_map[files[2].filename] = "tu_document"

    upload_tasks = [upload(f) for f in files if f]
    uploaded_files_list = await asyncio.gather(*upload_tasks)

    # Собираем словарь с правильными ключами
    result_dict = {}
    for filename, file_obj in uploaded_files_list:
        key = file_map.get(filename)
        if key:
            result_dict[key] = file_obj

    return result_dict


def _build_multimodal_prompt(stage: str, req_type: str, files: Dict[str, Any]) -> List[Any]:
    """Формирование мультимодального промпта для Gemini API с ссылками на файлы."""
    stage_prompt = PROMPTS.get(stage, PROMPTS["ФЭ"])

    prompt_parts = [
        stage_prompt,
        "\n\nТЕХНИЧЕСКОЕ ЗАДАНИЕ:",
        files["tz_document"],
        "\n\nПРОЕКТНАЯ ДОКУМЕНТАЦИЯ:",
        files["doc_document"],
    ]

    if "tu_document" in files:
        prompt_parts.extend(["\n\nТЕХНИЧЕСКИЕ УСЛОВИЯ:", files["tu_document"]])

    prompt_parts.append(f"""
ЗАДАЧА:
Проанализируй соответствие проектной документации требованиям технического задания{' и технических условий' if 'tu_document' in files else ''}.

Верни результат в формате JSON со следующей структурой:
{{
  "requirements": [
    {{
      "number": 1,
      "requirement": "Текст требования из ТЗ",
      "status": "Исполнено|Частично исполнено|Не исполнено|Требует уточнения",
      "confidence": 95,
      "solution_description": "Описание найденного решения",
      "reference": "Документ, страница/лист",
      "discrepancies": "Выявленные несоответствия",
      "recommendations": "Рекомендации по доработке"
    }}
  ],
  "summary": "Общая сводка по результатам анализа"
}}

ВАЖНО: Верни ТОЛЬКО валидный JSON, без дополнительного текста.
""")
    return prompt_parts


async def _call_gemini_api(prompt: List[Any]) -> str:
    """Вызов Gemini API с мультимодальным промптом."""
    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = await model.generate_content_async(
            prompt,
            generation_config=genai.types.GenerationConfig(temperature=TEMPERATURE)
        )
        return response.text
    except Exception as e:
        logger.error(f"Ошибка при вызове Gemini API: {e}", exc_info=True)
        raise


def _parse_analysis_response(response_text: str, stage: str, req_type: str) -> AnalysisResponse:
    """Парсинг JSON ответа от AI в Pydantic модель."""
    try:
        cleaned_response = response_text.strip().removeprefix("```json").removesuffix("```").strip()
        data = json.loads(cleaned_response)

        requirements = [RequirementAnalysis(**req) for req in data.get("requirements", [])]

        return AnalysisResponse(
            stage=stage,
            req_type=req_type,
            requirements=requirements,
            summary=data.get("summary", "Анализ завершен")
        )
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка парсинга JSON: {e}. Ответ AI: {response_text}")
        raise ValueError(f"Не удалось обработать ответ от AI. Ошибка парсинга JSON.")


# ============================
# ЗАПУСК СЕРВЕРА
# ============================

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
