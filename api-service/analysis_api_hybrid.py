"""
FastAPI сервис для анализа документации с использованием гибридного подхода:
- ТЗ/ТУ: ручной парсинг и сегментация требований
- Чертежи: OpenAI Assistants API с File Search для анализа
"""
import os
import json
import logging
import asyncio
import warnings
from typing import List, Optional, Dict, Any
from pathlib import Path
import fitz  # pymupdf
from tenacity import retry, stop_after_attempt, wait_exponential

# Отключаем warnings о deprecation
warnings.filterwarnings("ignore", category=DeprecationWarning, module="openai")

import uvicorn
from fastapi import FastAPI, HTTPException, Form, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError
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

logger.info(f"🚀 Используется OpenAI API (VISION MODE): {OPENAI_MODEL}")
logger.info("📋 Архитектура: ТЗ/ТУ парсинг вручную + Чертежи через Vision API")


# ============================
# СИСТЕМА ПРОМПТОВ
# ============================

def load_prompts() -> Dict[str, str]:
    """Загружает промпты из файлов в папке prompts."""
    prompts = {}
    prompts_dir = Path(__file__).parent.parent / "prompts"

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
            logger.info(f"✅ Загружен промпт для стадии {stage}")
        except FileNotFoundError:
            logger.error(f"❌ Не найден файл промпта: {file_path}")
            raise FileNotFoundError(f"Файл промпта не найден: {file_path}")

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
            logger.info(f"✅ Загружены предзагруженные ТУ для стадии {stage}")
        except FileNotFoundError:
            logger.warning(f"⚠️ Не найден файл ТУ: {file_path}")
            tu_prompts[stage] = ""

    return tu_prompts

# Загружаем промпты при инициализации
PROMPTS = load_prompts()
TU_PROMPTS = load_tu_prompts()

# ============================
# PDF PROCESSING ФУНКЦИИ
# ============================

async def extract_pdf_pages_as_images(doc_content: bytes, filename: str, max_pages: int = 50) -> List[str]:
    """
    Извлекает страницы PDF как base64-encoded изображения для Vision API.
    Возвращает список base64 строк.
    """
    logger.info(f"📄 Извлечение страниц из {filename} как изображений...")

    def _extract():
        import base64
        from PIL import Image
        import io

        doc = fitz.open(stream=doc_content, filetype="pdf")
        images = []

        total_pages = min(len(doc), max_pages)
        logger.info(f"📄 Обрабатываем {total_pages} страниц из {len(doc)}")

        for page_num in range(total_pages):
            page = doc[page_num]
            # Рендерим страницу в изображение (150 DPI для хорошего качества)
            pix = page.get_pixmap(dpi=150)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # Конвертируем в base64
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=85)
            base64_image = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
            images.append(base64_image)

        doc.close()
        logger.info(f"✅ Извлечено {len(images)} страниц")
        return images

    return await asyncio.to_thread(_extract)


def get_analysis_system_prompt(stage: str, req_type: str) -> str:
    """
    Возвращает system prompt для анализа документации.
    """
    stage_prompt = PROMPTS.get(stage, PROMPTS["ФЭ"])

    return f"""{stage_prompt}

Ты — эксперт по анализу строительной документации. Твоя задача:

1. Получить требование из {req_type}
2. Найти в проектной документации (чертежах) решение этого требования
3. Вернуть анализ в JSON формате:

{{
  "number": <номер требования>,
  "requirement": "<текст требования>",
  "status": "<Полностью исполнено|Частично исполнено|Не исполнено|Требует уточнения>",
  "confidence": <0-100>,
  "solution_description": "<краткое описание как реализовано>",
  "reference": "<конкретная ссылка: номер листа, раздел, страница>",
  "discrepancies": "<несоответствия или '-'>",
  "recommendations": "<рекомендации или '-'>"
}}

ВАЖНО:
- Внимательно изучи все предоставленные страницы чертежей
- Указывай КОНКРЕТНЫЕ ссылки (номера листов, разделы, страницы)
- Анализируй как текст, так и графические элементы на чертежах
- Если не нашел информацию, указывай status="Требует уточнения"
- Возвращай ТОЛЬКО JSON, без дополнительных пояснений
"""


async def analyze_requirement_with_vision(
    system_prompt: str,
    doc_images: List[str],
    requirement: Dict[str, Any],
    request: Request
) -> Optional['RequirementAnalysis']:
    """
    Анализирует одно требование через Vision API с изображениями чертежей.
    Возвращает RequirementAnalysis или None при отключении клиента.
    """
    if await request.is_disconnected():
        logger.warning(f"⚠️ Client disconnected before analyzing {requirement['trace_id']}")
        return None

    logger.info(f"🔍 Анализ требования {requirement['trace_id']}...")

    # Формируем content для Vision API
    content = [
        {
            "type": "text",
            "text": f"""Проанализируй следующее требование из ТЗ:

Номер: {requirement.get('number')}
Раздел: {requirement.get('section', 'Общие требования')}
Требование: {requirement['text']}

Найди в проектной документации (чертежах), как это требование выполнено.
Верни результат СТРОГО в JSON формате без дополнительного текста."""
        }
    ]

    # Добавляем изображения чертежей
    for idx, base64_image in enumerate(doc_images, 1):
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{base64_image}",
                "detail": "high"  # Высокое качество для детального анализа
            }
        })

    try:
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content}
            ],
            temperature=TEMPERATURE,
            max_tokens=2000
        )

        response_text = response.choices[0].message.content

        # Парсим JSON из ответа
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        if json_start != -1 and json_end > json_start:
            json_str = response_text[json_start:json_end]
            data = json.loads(json_str)

            return RequirementAnalysis(
                **data,
                section=requirement.get('section'),
                trace_id=requirement['trace_id']
            )
        else:
            raise ValueError("No JSON found in response")

    except (json.JSONDecodeError, ValidationError) as e:
        logger.error(f"❌ Failed to parse response for {requirement['trace_id']}: {e}")
        return RequirementAnalysis(
            number=requirement.get('number', 0),
            requirement=requirement['text'],
            status="Требует уточнения",
            confidence=50,
            solution_description="Не удалось получить ответ",
            reference="-",
            discrepancies="Ошибка парсинга ответа",
            recommendations="Проверьте вручную",
            section=requirement.get('section'),
            trace_id=requirement['trace_id']
        )
    except Exception as e:
        logger.error(f"❌ Error analyzing {requirement['trace_id']}: {e}")
        return RequirementAnalysis(
            number=requirement.get('number', 0),
            requirement=requirement['text'],
            status="Требует уточнения",
            confidence=0,
            solution_description="Ошибка анализа",
            reference="-",
            discrepancies=str(e),
            recommendations="Повторите анализ",
            section=requirement.get('section'),
            trace_id=requirement['trace_id']
        )


# ============================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ТЗ/ТУ
# ============================

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
async def extract_text_from_pdf(content: bytes, filename: str) -> str:
    """Извлекает текст из PDF. Использует OCR если нет текстового слоя."""
    import base64
    from PIL import Image
    import io

    text = ""
    doc = fitz.open(stream=content, filetype="pdf")
    is_scanned = True

    # Сначала пробуем извлечь текст напрямую
    for page in doc:
        page_text = page.get_text()
        if page_text.strip():
            is_scanned = False
            text += page_text + "\n\n"

    # Если текста нет - используем OCR через OpenAI Vision
    if is_scanned or not text.strip():
        logger.warning(f"⚠️ Файл {filename} отсканирован, применяем OCR через OpenAI Vision...")

        for page_num, page in enumerate(doc):
            # Рендерим страницу в изображение
            pix = page.get_pixmap(dpi=150)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # Конвертируем в base64
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=85)
            base64_image = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')

            # OCR через Vision
            logger.info(f"📄 OCR страницы {page_num + 1}/{len(doc)} из {filename}")
            response = await client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Извлеки весь текст с этого изображения. Сохрани структуру, номера пунктов, таблицы. Верни только текст без комментариев."
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                            }
                        ]
                    }
                ],
                temperature=0.0,
                max_tokens=4000
            )

            page_text = response.choices[0].message.content
            text += f"\n\n--- Страница {page_num + 1} ---\n\n{page_text}"

        logger.info(f"✅ OCR завершен для {filename}, извлечено {len(text)} символов")

    doc.close()

    if not text.strip():
        logger.error(f"❌ Не удалось извлечь текст из {filename}")
        return "[Документ пуст или не удалось распознать текст]"

    return text.strip()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
async def segment_requirements(tz_text: str) -> List[Dict[str, Any]]:
    """Сегментирует ТЗ на отдельные требования используя GPT."""
    prompt = f"""Проанализируй следующий текст ТЗ и извлеки из него список требований.

Для каждого требования укажи:
- number: порядковый номер (целое число)
- text: полный текст требования
- section: название раздела, к которому относится требование
- trace_id: уникальный ID в формате 'req-{{number}}'

Верни результат СТРОГО в JSON формате:
{{"requirements": [{{"number": 1, "text": "...", "section": "...", "trace_id": "req-1"}}]}}

Текст ТЗ:
{tz_text[:10000]}"""  # Ограничиваем до 10000 символов

    response = await client.chat.completions.create(
        model="gpt-4o-mini",  # Дешевая модель для сегментации
        messages=[{"role": "user", "content": prompt}],
        temperature=TEMPERATURE,
        response_format={"type": "json_object"}
    )

    try:
        data = json.loads(response.choices[0].message.content)
        requirements = data.get("requirements", [])
        logger.info(f"✅ Извлечено {len(requirements)} требований")
        return requirements
    except json.JSONDecodeError as e:
        logger.error(f"❌ Failed to parse requirements JSON: {e}")
        raise ValueError("Failed to parse requirements JSON")


async def _get_file_size(file: UploadFile) -> int:
    """Получает размер файла в байтах."""
    content = await file.read()
    await file.seek(0)
    return len(content)


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
    section: Optional[str] = None
    trace_id: Optional[str] = None


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
    title="Document Analysis API (Vision Mode)",
    description="API для анализа строительной документации с использованием Vision API",
    version="6.0.0-vision"
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
        "service": "Document Analysis API (VISION MODE)",
        "architecture": "TZ/TU manual parsing + Drawings via Vision API",
        "provider": "openai",
        "model": OPENAI_MODEL,
        "max_file_size_mb": MAX_FILE_SIZE_MB
    }


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_documentation(
    request: Request,
    stage: str = Form(...),
    check_tu: bool = Form(False),
    req_type: str = Form("ТЗ"),
    tz_document: UploadFile = File(...),
    doc_document: UploadFile = File(...),
    tu_document: Optional[UploadFile] = File(None)
):
    """
    Гибридный анализ документации:
    - ТЗ/ТУ: ручной парсинг и сегментация
    - Чертежи: Vision API для анализа страниц
    """
    try:
        # Проверяем, не отключился ли клиент
        if await request.is_disconnected():
            logger.warning("⚠️ Client disconnected before analysis started. Aborting.")
            raise HTTPException(status_code=499, detail="Client disconnected")

        logger.info(f"📋 [HYBRID] Получен запрос на анализ. Стадия: {stage}, check_tu: {check_tu}")

        # ============================================================
        # ЭТАП 1: Парсинг ТЗ/ТУ (ручной, быстрый, контролируемый)
        # ============================================================

        # Проверка размера файлов
        files_to_check = [tz_document, doc_document]
        if tu_document:
            files_to_check.append(tu_document)

        for file in files_to_check:
            file_size = await _get_file_size(file)
            if file_size > MAX_FILE_SIZE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"Файл {file.filename} слишком большой ({file_size / 1024 / 1024:.2f} MB). Максимум: {MAX_FILE_SIZE_MB} MB"
                )

        # Read contents
        await tz_document.seek(0)
        await doc_document.seek(0)
        if tu_document:
            await tu_document.seek(0)

        tz_content = await tz_document.read()
        doc_content = await doc_document.read()
        tu_content = None
        if tu_document:
            tu_content = await tu_document.read()

        logger.info(f"📊 File sizes - TZ: {len(tz_content) / 1024:.1f} KB, DOC: {len(doc_content) / 1024:.1f} KB")

        # Extract TZ text (ручной парсинг)
        logger.info("📄 [STEP 1/4] Extracting text from TZ...")
        if await request.is_disconnected():
            logger.warning("⚠️ Client disconnected during TZ extraction")
            return {"error": "Client disconnected"}

        tz_text = await extract_text_from_pdf(tz_content, tz_document.filename)

        # Handle TU if needed
        has_tu = check_tu and (tu_content is not None or stage in TU_PROMPTS)
        if has_tu:
            logger.info("📄 Adding TU to requirements...")
            tu_text = await extract_text_from_pdf(tu_content, tu_document.filename) if tu_content else TU_PROMPTS.get(stage, "")
            tz_text += "\n\n=== Технические условия (ТУ) ===\n" + tu_text

        # Segment requirements (контролируемая сегментация)
        logger.info("✂️ [STEP 2/4] Segmenting requirements from TZ/TU...")
        if await request.is_disconnected():
            logger.warning("⚠️ Client disconnected during segmentation")
            return {"error": "Client disconnected"}

        requirements = await segment_requirements(tz_text)

        if not requirements:
            raise HTTPException(status_code=400, detail="No requirements extracted from TZ")

        logger.info(f"✅ Extracted {len(requirements)} requirements")

        # ============================================================
        # ЭТАП 2: Конвертация чертежей в изображения
        # ============================================================

        logger.info("📤 [STEP 3/4] Converting project documentation to images...")
        if await request.is_disconnected():
            logger.warning("⚠️ Client disconnected before conversion")
            return {"error": "Client disconnected"}

        doc_images = await extract_pdf_pages_as_images(doc_content, doc_document.filename)

        # ============================================================
        # ЭТАП 3: Подготовка system prompt
        # ============================================================

        system_prompt = get_analysis_system_prompt(stage, "ТЗ+ТУ" if has_tu else "ТЗ")

        # ============================================================
        # ЭТАП 4: Анализ каждого требования через Vision API
        # ============================================================

        logger.info(f"🔍 [STEP 4/4] Analyzing {len(requirements)} requirements with Vision API...")
        analyzed_reqs = []

        for idx, req in enumerate(requirements, 1):
            if await request.is_disconnected():
                logger.warning(f"⚠️ Client disconnected at requirement {idx}/{len(requirements)}")
                return {"error": "Client disconnected"}

            logger.info(f"🔍 [{idx}/{len(requirements)}] Analyzing: {req.get('trace_id')}")

            result = await analyze_requirement_with_vision(
                system_prompt=system_prompt,
                doc_images=doc_images,
                requirement=req,
                request=request
            )

            if result is None:  # Client disconnected
                return {"error": "Client disconnected"}

            analyzed_reqs.append(result)

        # ============================================================
        # ЭТАП 5: Генерация сводки
        # ============================================================

        logger.info("📝 Generating summary...")
        if await request.is_disconnected():
            logger.warning("⚠️ Client disconnected before summary")
            await cleanup_assistant_resources(assistant_id, file_id)
            return {"error": "Client disconnected"}

        # Статистика для сводки
        total = len(analyzed_reqs)
        completed = sum(1 for r in analyzed_reqs if r.status == "Полностью исполнено")
        partial = sum(1 for r in analyzed_reqs if r.status == "Частично исполнено")
        not_done = sum(1 for r in analyzed_reqs if r.status == "Не исполнено")
        unclear = sum(1 for r in analyzed_reqs if r.status == "Требует уточнения")

        summary = f"""Анализ документации завершен.

Проанализировано требований: {total}
- Полностью исполнено: {completed} ({completed/total*100:.1f}%)
- Частично исполнено: {partial} ({partial/total*100:.1f}%)
- Не исполнено: {not_done} ({not_done/total*100:.1f}%)
- Требует уточнения: {unclear} ({unclear/total*100:.1f}%)

Средняя достоверность: {sum(r.confidence for r in analyzed_reqs)/total:.1f}%"""

        # ============================================================
        # Возврат результата
        # ============================================================

        parsed_result = AnalysisResponse(
            stage=stage,
            req_type="ТЗ+ТУ" if has_tu else "ТЗ",
            requirements=analyzed_reqs,
            summary=summary
        )

        logger.info(f"✅ [HYBRID] Анализ завершен успешно. Проанализировано {len(analyzed_reqs)} требований.")
        return parsed_result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [HYBRID] Ошибка при анализе: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка анализа: {str(e)}")


# ============================
# ЗАПУСК СЕРВЕРА
# ============================

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
