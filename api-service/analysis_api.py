"""
FastAPI сервис для анализа документации с использованием Google Gemini API
Работает через VPN/SOCKS прокси
"""
import os
import json
import logging
from typing import List, Optional
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
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

# Настройки модели
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.1"))


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

class DocumentInfo(BaseModel):
    """Информация о документе"""
    filename: str
    content_summary: str  # Краткое содержание/извлеченный текст


class AnalysisRequest(BaseModel):
    """Запрос на анализ документации"""
    stage: str  # Стадия: ГК, ФЭ, ЭП, ПД, РД
    req_type: str  # Тип требований: ТЗ, ТУ_*
    tz_document: DocumentInfo  # Техническое задание
    doc_document: DocumentInfo  # Проектная документация
    tu_document: Optional[DocumentInfo] = None  # Технические условия (опционально)


class RequirementAnalysis(BaseModel):
    """Результат анализа одного требования"""
    number: int
    requirement: str
    status: str  # Исполнено, Частично исполнено, Не исполнено, Требует уточнения
    confidence: int  # 0-100
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
    version="1.0.0"
)

# CORS для доступа из Gradio UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене указать конкретный домен UI
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
        "model": GEMINI_MODEL
    }


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_documentation(request: AnalysisRequest):
    """
    Основной endpoint для анализа документации

    Args:
        request: Запрос с информацией о документах и параметрах анализа

    Returns:
        AnalysisResponse: Результаты анализа в структурированном виде
    """
    try:
        logger.info(f"Получен запрос на анализ. Стадия: {request.stage}, Тип: {request.req_type}")

        # Получение промпта для стадии
        stage_prompt = PROMPTS.get(request.stage, PROMPTS["ФЭ"])

        # Формирование полного промпта для Gemini
        full_prompt = _build_gemini_prompt(request, stage_prompt)

        # Вызов Gemini API
        logger.info("Отправка запроса в Google Gemini API...")
        analysis_result = await _call_gemini_api(full_prompt)

        # Парсинг результата
        logger.info("Парсинг результатов анализа...")
        parsed_result = _parse_gemini_response(analysis_result, request.stage, request.req_type)

        logger.info("Анализ завершен успешно")
        return parsed_result

    except Exception as e:
        logger.error(f"Ошибка при анализе документации: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка анализа: {str(e)}")


# ============================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================

def _build_gemini_prompt(request: AnalysisRequest, stage_prompt: str) -> str:
    """Формирование промпта для Gemini API"""

    requirements_info = ""
    if request.tu_document:
        requirements_info = f"\n\nТЕХНИЧЕСКИЕ УСЛОВИЯ:\nФайл: {request.tu_document.filename}\n{request.tu_document.content_summary}"

    prompt = f"""
{stage_prompt}

ТЕХНИЧЕСКОЕ ЗАДАНИЕ:
Файл: {request.tz_document.filename}
{request.tz_document.content_summary}

ПРОЕКТНАЯ ДОКУМЕНТАЦИЯ:
Файл: {request.doc_document.filename}
{request.doc_document.content_summary}
{requirements_info}

ЗАДАЧА:
Проанализируй соответствие проектной документации требованиям технического задания{' и технических условий' if request.tu_document else ''}.

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
"""
    return prompt


async def _call_gemini_api(prompt: str) -> str:
    """Вызов Google Gemini API"""
    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = await model.generate_content_async(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=TEMPERATURE
            )
        )
        return response.text

    except Exception as e:
        logger.error(f"Ошибка при вызове Gemini API: {e}")
        raise


def _parse_gemini_response(gemini_response: str, stage: str, req_type: str) -> AnalysisResponse:
    """Парсинг ответа от Gemini в структурированный формат"""
    try:
        # Очистка response от markdown если есть
        cleaned_response = gemini_response.strip()
        if cleaned_response.startswith("```json"):
            cleaned_response = cleaned_response[7:]
        if cleaned_response.startswith("```"):
            cleaned_response = cleaned_response[3:]
        if cleaned_response.endswith("```"):
            cleaned_response = cleaned_response[:-3]
        cleaned_response = cleaned_response.strip()

        # Парсинг JSON
        data = json.loads(cleaned_response)

        # Преобразование в Pydantic модели
        requirements = [
            RequirementAnalysis(**req) for req in data.get("requirements", [])
        ]

        return AnalysisResponse(
            stage=stage,
            req_type=req_type,
            requirements=requirements,
            summary=data.get("summary", "Анализ завершен")
        )

    except json.JSONDecodeError as e:
        logger.error(f"Ошибка парсинга JSON от Gemini: {e}")
        logger.error(f"Ответ Gemini: {gemini_response}")

        # Возвращаем заглушку если не удалось распарсить
        return AnalysisResponse(
            stage=stage,
            req_type=req_type,
            requirements=[
                RequirementAnalysis(
                    number=1,
                    requirement="Ошибка парсинга ответа от Gemini",
                    status="Требует уточнения",
                    confidence=0,
                    solution_description="Не удалось обработать ответ",
                    reference="-",
                    discrepancies=f"Ошибка: {str(e)}",
                    recommendations="Проверьте формат промпта"
                )
            ],
            summary="Ошибка обработки ответа от Gemini API"
        )


# ============================
# ЗАПУСК СЕРВЕРА
# ============================

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
