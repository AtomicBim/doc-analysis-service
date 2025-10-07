"""
FastAPI сервис для анализа документации с использованием OpenAI API.
Использует Assistants API с File Search для обработки строительных чертежей в PDF.
"""
import os
import json
import logging
import asyncio
import warnings
from typing import List, Optional, Dict, Any
from pathlib import Path

# Отключаем warnings о deprecation Assistants API
warnings.filterwarnings("ignore", category=DeprecationWarning, module="openai")

import uvicorn
from fastapi import FastAPI, HTTPException, Form, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import AsyncOpenAI
from dotenv import load_dotenv

# ============================
# КОНФИГУРАЦИЯ
# ============================

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Инициализация OpenAI API
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY не установлен в переменных окружения!")
    raise ValueError("OPENAI_API_KEY is required")

client = AsyncOpenAI(api_key=OPENAI_API_KEY)
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.1"))
MAX_FILE_SIZE_MB = 40
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

logger.info(f"Используется OpenAI API: {OPENAI_MODEL}")


# ============================
# СИСТЕМА ПРОМПТОВ
# ============================

def load_prompts() -> Dict[str, str]:
    """Загружает промпты из файлов в папке prompts."""
    prompts = {}
    prompts_dir = Path(__file__).parent.parent / "prompts"
    
    # Маппинг стадий на файлы
    stage_files = {
        "ГК": "gk_prompt.txt",
        "ФЭ": "fe_prompt.txt", 
        "ЭП": "ep_prompt.txt"
    }
    
    for stage, filename in stage_files.items():
        file_path = prompts_dir / filename
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                prompts[stage] = f.read().strip()
            logger.info(f"Загружен промпт для стадии {stage} из {file_path}")
        except FileNotFoundError:
            logger.error(f"Не найден файл промпта: {file_path}")
            raise FileNotFoundError(f"Файл промпта не найден: {file_path}")
        except Exception as e:
            logger.error(f"Ошибка загрузки промпта {stage}: {e}")
            raise
    
    return prompts


def load_tu_prompts() -> Dict[str, str]:
    """Загружает предзагруженные ТУ для стадий ФЭ и ЭП."""
    tu_prompts: Dict[str, str] = {}
    prompts_dir = Path(__file__).parent.parent / "prompts"

    tu_stage_files = {
        "ФЭ": "tu_fe.txt",
        "ЭП": "tu_ep.txt",
    }

    for stage, filename in tu_stage_files.items():
        file_path = prompts_dir / filename
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                tu_prompts[stage] = f.read().strip()
            logger.info(f"Загружены предзагруженные ТУ для стадии {stage} из {file_path}")
        except FileNotFoundError:
            logger.error(f"Не найден файл предзагруженных ТУ: {file_path}")
            raise FileNotFoundError(f"Файл предзагруженных ТУ не найден: {file_path}")
        except Exception as e:
            logger.error(f"Ошибка загрузки ТУ {stage}: {e}")
            raise

    return tu_prompts

# Загружаем промпты при инициализации
PROMPTS = load_prompts()
TU_PROMPTS = load_tu_prompts()

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
    description="API для анализа строительной документации с использованием OpenAI",
    version="4.0.0"
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
        "provider": "openai",
        "model": OPENAI_MODEL,
        "max_file_size_mb": MAX_FILE_SIZE_MB
    }

@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_documentation(
    stage: str = Form(...),
    check_tu: bool = Form(False),
    req_type: str = Form("ТЗ"),
    tz_document: UploadFile = File(...),
    doc_document: UploadFile = File(...),
    tu_document: Optional[UploadFile] = File(None)
):
    """
    Основной endpoint для анализа документации.
    Принимает файлы и метаданные в multipart/form-data.
    """
    try:
        logger.info(f"Получен запрос на анализ. Стадия: {stage}, check_tu: {check_tu}")

        # Бизнес-валидация: если включена проверка ТУ и стадия ФЭ/ЭП без файла ТУ — загрузим предзагруженный текст
        # Стадии ПД/РД больше не поддерживаются

        # Проверка размера файлов
        files_to_check = [tz_document, doc_document]
        if tu_document:
            files_to_check.append(tu_document)

        for file in files_to_check:
            file_size = await _get_file_size(file)
            if file_size > MAX_FILE_SIZE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"Файл {file.filename} слишком большой ({file_size / 1024 / 1024:.2f} MB). Максимальный размер: {MAX_FILE_SIZE_MB} MB"
                )

        # Загружаем файлы в OpenAI
        logger.info("Загрузка файлов в OpenAI...")
        file_ids = await _upload_files_to_openai(
            [tz_document, doc_document, tu_document]
        )

        # Если включена проверка ТУ и стадия ФЭ/ЭП, а файл ТУ не загружен — добавляем предзагруженный текст ТУ как виртуальный файл
        has_preloaded_tu = False
        if check_tu and tu_document is None and stage in ["ФЭ", "ЭП"]:
            tu_text = TU_PROMPTS.get(stage)
            if not tu_text:
                raise HTTPException(status_code=500, detail=f"Предзагруженные ТУ для стадии {stage} недоступны")

            logger.info("Загрузка предзагруженных ТУ как виртуального файла...")
            uploaded_file = await client.files.create(
                file=(f"preloaded_tu_{stage}.txt", tu_text.encode("utf-8")),
                purpose="assistants"
            )
            file_ids.append(uploaded_file.id)
            has_preloaded_tu = True

        # Создаём ассистента с file search
        logger.info("Создание ассистента для анализа...")
        assistant = await client.beta.assistants.create(
            name="Document Analyzer",
            instructions="Ты эксперт по анализу строительной документации и чертежей. Анализируй PDF документы внимательно, обращая особое внимание на графические элементы чертежей.",
            model=OPENAI_MODEL,
            tools=[{"type": "file_search"}]
        )

        # Создаём thread и отправляем запрос
        logger.info("Отправка запроса на анализ...")
        has_tu = check_tu and (tu_document is not None or has_preloaded_tu)

        analysis_result_text = await _run_analysis_with_assistant(
            assistant.id,
            file_ids,
            stage,
            "ТЗ+ТУ" if has_tu else "ТЗ",
            has_tu
        )

        # Парсинг результата
        logger.info("Парсинг результатов анализа...")
        parsed_result = _parse_analysis_response(analysis_result_text, stage, "ТЗ+ТУ" if has_tu else "ТЗ")

        # Очистка ресурсов
        logger.info("Очистка ресурсов...")
        await _cleanup_resources(assistant.id, file_ids)

        logger.info("Анализ завершен успешно")
        return parsed_result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при анализе документации: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка анализа: {str(e)}")

# ============================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================

async def _get_file_size(file: UploadFile) -> int:
    """Получает размер файла в байтах."""
    content = await file.read()
    await file.seek(0)  # Возвращаем указатель в начало
    return len(content)


async def _upload_files_to_openai(
    files: List[Optional[UploadFile]]
) -> List[str]:
    """Загружает файлы в OpenAI."""
    file_ids = []

    for file in files:
        if file is None:
            continue

        logger.info(f"Загружается файл: {file.filename}")
        content = await file.read()

        # Загружаем файл в OpenAI
        uploaded_file = await client.files.create(
            file=(file.filename, content),
            purpose="assistants"
        )
        file_ids.append(uploaded_file.id)

        logger.info(f"Файл {file.filename} загружен (ID: {uploaded_file.id})")

    return file_ids


async def _run_analysis_with_assistant(
    assistant_id: str,
    file_ids: List[str],
    stage: str,
    req_type: str,
    has_tu: bool
) -> str:
    """Запускает анализ с использованием ассистента."""
    stage_prompt = PROMPTS.get(stage, PROMPTS["ФЭ"])

    prompt = f"""{stage_prompt}

ЗАДАЧА:
Проанализируй соответствие проектной документации требованиям технического задания{' и технических условий' if has_tu else ''}.

ВАЖНО:
- Проектная документация представляет собой строительные чертежи в формате PDF
- Обрати особое внимание на графические элементы, размеры, схемы, планы
- Проверь текстовые описания, спецификации и таблицы на чертежах

Верни результат СТРОГО в формате JSON со следующей структурой:
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

    # Создаём thread
    thread = await client.beta.threads.create()

    # Добавляем сообщение с прикрепленными файлами
    await client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=prompt,
        attachments=[{"file_id": fid, "tools": [{"type": "file_search"}]} for fid in file_ids]
    )

    # Запускаем run
    run = await client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant_id
    )

    # Ждём завершения
    while run.status in ["queued", "in_progress"]:
        await asyncio.sleep(1)
        run = await client.beta.threads.runs.retrieve(
            thread_id=thread.id,
            run_id=run.id
        )

    if run.status != "completed":
        raise Exception(f"Run завершился со статусом: {run.status}")

    # Получаем ответ
    messages = await client.beta.threads.messages.list(thread_id=thread.id)
    response_message = messages.data[0]

    # Извлекаем текст из ответа
    response_text = response_message.content[0].text.value

    # Удаляем thread
    await client.beta.threads.delete(thread.id)

    return response_text


async def _cleanup_resources(assistant_id: str, file_ids: List[str]):
    """Удаляет созданные ресурсы."""
    try:
        # Удаляем ассистента
        await client.beta.assistants.delete(assistant_id)

        # Удаляем файлы
        for file_id in file_ids:
            try:
                await client.files.delete(file_id)
            except Exception as e:
                logger.warning(f"Не удалось удалить файл {file_id}: {e}")

        logger.info("Ресурсы успешно очищены")
    except Exception as e:
        logger.warning(f"Ошибка при очистке ресурсов: {e}")


def _parse_analysis_response(response_text: str, stage: str, req_type: str) -> AnalysisResponse:
    """Парсинг JSON ответа от AI в Pydantic модель."""
    try:
        # Убираем возможные markdown блоки
        cleaned_response = response_text.strip()
        if cleaned_response.startswith("```"):
            # Находим JSON между ```json и ```
            start = cleaned_response.find("{")
            end = cleaned_response.rfind("}") + 1
            if start != -1 and end > start:
                cleaned_response = cleaned_response[start:end]

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
        raise ValueError(f"Не удалось обработать ответ от AI. Ошибка парсинга JSON: {str(e)}")


# ============================
# ЗАПУСК СЕРВЕРА
# ============================

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
