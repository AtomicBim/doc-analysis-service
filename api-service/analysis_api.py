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
import fitz  # pymupdf
from PIL import Image
import io
from tenacity import retry, stop_after_attempt, wait_exponential
import base64

# Отключаем warnings о deprecation Assistants API
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
DPI = int(os.getenv("DPI", "300"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "5"))
TOP_K = int(os.getenv("TOP_K", "5"))

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
    request: Request,
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
        # Проверяем, не отключился ли клиент
        if await request.is_disconnected():
            logger.warning("Client disconnected before analysis started. Aborting.")
            raise HTTPException(status_code=499, detail="Client disconnected")
        logger.info(f"Получен запрос на анализ. Стадия: {stage}, check_tu: {check_tu}")

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

        # Read contents (after _get_file_size already read them, need to seek back)
        await tz_document.seek(0)
        await doc_document.seek(0)
        if tu_document:
            await tu_document.seek(0)

        tz_content = await tz_document.read()
        doc_content = await doc_document.read()
        tu_content = None
        if tu_document:
            tu_content = await tu_document.read()

        logger.info(f"File sizes - TZ: {len(tz_content)} bytes, DOC: {len(doc_content)} bytes")

        # Extract TZ text
        logger.info("Extracting text from TZ...")
        if await request.is_disconnected():
            logger.warning("Client disconnected during TZ extraction. Aborting.")
            return {"error": "Client disconnected"}
        tz_text = await extract_text_from_pdf(tz_content, tz_document.filename)

        # Segment requirements
        logger.info("Segmenting requirements...")
        if await request.is_disconnected():
            logger.warning("Client disconnected during requirements segmentation. Aborting.")
            return {"error": "Client disconnected"}
        requirements = await segment_requirements(tz_text)

        if not requirements:
            raise HTTPException(status_code=400, detail="No requirements extracted from TZ")

        # Ingest doc
        logger.info("Ingesting project documentation...")
        if await request.is_disconnected():
            logger.warning("Client disconnected during doc ingestion. Aborting.")
            return {"error": "Client disconnected"}
        doc_pages = await ingest_doc(doc_content, doc_document.filename)

        # TODO: Handle TU similarly if check_tu
        has_tu = check_tu and (tu_content is not None or stage in TU_PROMPTS)
        # For simplicity, append TU text to tz_text if present
        if has_tu:
            tu_text = await extract_text_from_pdf(tu_content, tu_document.filename) if tu_content else TU_PROMPTS.get(stage, "")
            tz_text += "\n\nTU:\n" + tu_text
            requirements = await segment_requirements(tz_text)  # Re-segment with TU

        # For now, placeholder for retrieval and analysis
        # Will replace in next edits
        logger.info("Retrieving relevant pages...")
        if await request.is_disconnected():
            logger.warning("Client disconnected before retrieval. Aborting.")
            return {"error": "Client disconnected"}
        all_relevant_pages = {}
        for req in requirements:
            if await request.is_disconnected():
                logger.warning("Client disconnected during page retrieval. Aborting.")
                return {"error": "Client disconnected"}
            all_relevant_pages[req['trace_id']] = await retrieve_relevant_pages(req['text'], doc_pages)

        logger.info("Analyzing requirements in batches...")
        analyzed_reqs = []
        for i in range(0, len(requirements), BATCH_SIZE):
            if await request.is_disconnected():
                logger.warning(f"Client disconnected during batch {i // BATCH_SIZE + 1}. Aborting.")
                return {"error": "Client disconnected"}
            batch = requirements[i:i + BATCH_SIZE]
            analyzed_batch = await analyze_batch(batch, all_relevant_pages, stage, "ТЗ+ТУ" if has_tu else "ТЗ")
            analyzed_reqs.extend(analyzed_batch)

        # Generate summary
        if await request.is_disconnected():
            logger.warning("Client disconnected before summary generation. Aborting.")
            return {"error": "Client disconnected"}
        summary_prompt = f"Summarize analysis of {len(analyzed_reqs)} requirements: {json.dumps([r.dict() for r in analyzed_reqs])}"
        summary_response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": summary_prompt}],
            temperature=TEMPERATURE
        )
        summary = summary_response.choices[0].message.content
        
        parsed_result = AnalysisResponse(
            stage=stage,
            req_type="ТЗ+ТУ" if has_tu else "ТЗ",
            requirements=analyzed_reqs,
            summary=summary
        )

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

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
async def extract_text_from_pdf(content: bytes, filename: str) -> str:
    """Extracts text from PDF. Uses OCR if no text layer."""
    text = ""
    doc = fitz.open(stream=content, filetype="pdf")
    is_scanned = True
    for page in doc:
        page_text = page.get_text()
        if page_text.strip():
            is_scanned = False
            text += page_text + "\n\n"
    
    if is_scanned:
        # OCR using OpenAI Vision
        for page_num, page in enumerate(doc):
            pix = page.get_pixmap(dpi=DPI)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            img_byte_arr = img_byte_arr.getvalue()
            base64_image = base64.b64encode(img_byte_arr).decode('utf-8')
            
            response = await client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Extract all text from this image accurately, preserving structure and formatting."},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{base64_image}"}
                            }
                        ]
                    }
                ],
                temperature=TEMPERATURE,
            )
            text += response.choices[0].message.content + "\n\n"
    
    doc.close()
    return text.strip()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
async def segment_requirements(tz_text: str) -> List[Dict[str, Any]]:
    """Segments TZ text into individual requirements using GPT."""
    prompt = f"""Parse the following TZ text into a list of requirements. Each requirement should have:
- number: integer or string identifier
- text: the full text of the requirement
- section: parent section or category
- trace_id: unique identifier like 'req-{{number}}'

Return STRICTLY as JSON: {{"requirements": [{{"number": ..., "text": ..., "section": ..., "trace_id": ...}}]}}

TZ text:
{tz_text}"""

    response = await client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=TEMPERATURE,
        response_format={"type": "json_object"}
    )
    
    try:
        data = json.loads(response.choices[0].message.content)
        return data.get("requirements", [])
    except json.JSONDecodeError:
        raise ValueError("Failed to parse requirements JSON")

async def ingest_doc(content: bytes, filename: str) -> List[Dict[str, str]]:
    """Ingests doc PDF into list of pages with text and base64 image."""
    if not content:
        raise ValueError(f"Empty content provided for file {filename}")

    pages = []
    doc = fitz.open(stream=content, filetype="pdf")
    for page_num, page in enumerate(doc):
        text = page.get_text()
        pix = page.get_pixmap(dpi=DPI)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        base64_image = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
        pages.append({
            "page_num": page_num + 1,
            "text": text.strip(),
            "image": base64_image
        })
    doc.close()
    return pages

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
async def get_embedding(text: str) -> List[float]:
    """Gets embedding for text using OpenAI. Truncates if exceeds token limit."""
    # text-embedding-3-small max tokens: 8191
    # Approximate: 1 token ≈ 4 chars, safe limit = 8000 tokens ≈ 32000 chars
    MAX_CHARS = 32000

    if len(text) > MAX_CHARS:
        logger.warning(f"Text exceeds {MAX_CHARS} chars ({len(text)}), truncating for embedding")
        text = text[:MAX_CHARS]

    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding

import numpy as np

async def retrieve_relevant_pages(req_text: str, doc_pages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Retrieves top-k relevant pages using embedding similarity."""
    if not doc_pages:
        return []

    req_emb = await get_embedding(req_text)
    page_embs = []
    for page in doc_pages:
        page_text = page['text'].strip()
        if page_text:
            page_embs.append(await get_embedding(page_text))
        else:
            page_embs.append([0] * len(req_emb))  # Zero vector for empty text

    similarities = [np.dot(req_emb, p_emb) / (np.linalg.norm(req_emb) * np.linalg.norm(p_emb) + 1e-8) for p_emb in page_embs]
    top_indices = np.argsort(similarities)[-TOP_K:][::-1]
    return [doc_pages[i] for i in top_indices]

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
async def analyze_batch(batch: List[Dict[str, Any]], all_relevant_pages: Dict[str, List[Dict[str, str]]], stage: str, req_type: str) -> List[RequirementAnalysis]:
    """Analyzes batch of requirements with multimodal context."""
    stage_prompt = PROMPTS.get(stage, PROMPTS["ФЭ"])
    
    messages = [{"role": "system", "content": stage_prompt}]
    
    content = [{"type": "text", "text": f"Analyze these requirements against the documentation. Return STRICTLY JSON as {AnalysisResponse.model_json_schema()} but only the requirements array."}]
    
    for req in batch:
        content.append({"type": "text", "text": f"Requirement {req['trace_id']}: {req['text']}"})
        for page in all_relevant_pages.get(req['trace_id'], []):
            content.append({"type": "text", "text": f"Page {page['page_num']} text: {page['text']}"})
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{page['image']}"}
            })
    
    messages.append({"role": "user", "content": content})
    
    response = await client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        temperature=TEMPERATURE,
        response_format={"type": "json_object"}
    )
    
    try:
        data = json.loads(response.choices[0].message.content)
        return [RequirementAnalysis(**item) for item in data.get("requirements", [])]
    except (json.JSONDecodeError, ValidationError) as e:
        logger.error(f"Invalid JSON or validation error: {e}")
        raise


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
