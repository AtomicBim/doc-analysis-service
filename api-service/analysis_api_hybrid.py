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
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import RateLimitError

# Отключаем warnings о deprecation
warnings.filterwarnings("ignore", category=DeprecationWarning, module="openai")

import uvicorn
from fastapi import FastAPI, HTTPException, Form, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError
from openai import AsyncOpenAI
from dotenv import load_dotenv
from config import (
    # Stage 1
    STAGE1_MAX_PAGES, STAGE1_DPI, STAGE1_QUALITY, STAGE1_MAX_PAGES_PER_REQUEST,
    STAGE1_STAMP_CROP, STAGE1_TOP_RIGHT_CROP, STAGE1_HEADER_CROP,
    # Stage 2
    STAGE2_MAX_PAGES, STAGE2_DPI, STAGE2_QUALITY, STAGE2_DETAIL, STAGE2_MAX_PAGES_PER_REQUEST,
    # Stage 3
    STAGE3_DPI, STAGE3_QUALITY, STAGE3_DETAIL, STAGE3_BATCH_SIZE, STAGE3_MAX_TOKENS, STAGE3_RETRY_ON_REFUSAL, STAGE3_MAX_PAGES_PER_REQUEST,
    # Stage 4
    STAGE4_ENABLED, STAGE4_SAMPLE_PAGES_PER_SECTION, STAGE4_DPI, STAGE4_QUALITY, STAGE4_DETAIL, STAGE4_MAX_TOKENS,
    # Retry
    RETRY_MAX_ATTEMPTS, RETRY_WAIT_EXPONENTIAL_MULTIPLIER, RETRY_WAIT_EXPONENTIAL_MAX,
    # OpenAI
    OPENAI_MODEL, OPENAI_TEMPERATURE,
    # Logging
    LOG_LEVEL, LOG_RESPONSE_PREVIEW_LENGTH, LOG_FULL_RESPONSE_ON_ERROR
)

# ============================
# КОНФИГУРАЦИЯ
# ============================

logging.basicConfig(level=getattr(logging, LOG_LEVEL), format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Инициализация OpenAI API
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY не установлен в переменных окружения!")
    raise ValueError("OPENAI_API_KEY is required")

client = AsyncOpenAI(api_key=OPENAI_API_KEY)
TEMPERATURE = OPENAI_TEMPERATURE
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

async def extract_pdf_pages_as_images(doc_content: bytes, filename: str, max_pages: int = 150, detail: str = "low", dpi: int = 100, quality: int = 70) -> List[str]:
    """
    Извлекает страницы PDF как base64-encoded изображения для Vision API.

    Args:
        detail: "low" (85 tokens/img) или "high" (765 tokens/img)
        dpi: качество рендеринга (100 для low, 150 для high)
        quality: JPEG качество (70 для low, 85 для high)
    """
    logger.info(f"📄 [IMG] Извлечение страниц из {filename} (detail={detail}, dpi={dpi}, quality={quality})...")

    def _extract():
        import base64
        from PIL import Image
        import io

        doc = fitz.open(stream=doc_content, filetype="pdf")
        images = []

        total_pages = min(len(doc), max_pages)
        logger.info(f"📄 [IMG] Обрабатываем {total_pages} страниц из {len(doc)}")

        for page_num in range(total_pages):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=dpi)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=quality)
            base64_image = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
            images.append(base64_image)

        doc.close()
        logger.info(f"✅ [IMG] Извлечено {len(images)} страниц")
        return images

    return await asyncio.to_thread(_extract)


async def extract_page_metadata(doc_content: bytes, filename: str, max_pages: int = None) -> List[Dict[str, Any]]:
    """
    Stage 1: Извлекает метаданные страниц (штамп, заголовки) через Vision API.
    Фокус на правый нижний угол (штамп), правый верхний, заголовки.
    """
    if max_pages is None:
        max_pages = STAGE1_MAX_PAGES

    logger.info(f"📋 [STAGE 1] Извлечение метаданных из {filename}...")

    def _extract_crops():
        import base64
        from PIL import Image
        import io

        doc = fitz.open(stream=doc_content, filetype="pdf")
        metadata_images = []

        total_pages = min(len(doc), max_pages)

        for page_num in range(total_pages):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=STAGE1_DPI)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # Вырезаем ключевые области для быстрого анализа
            width, height = img.size

            # Правый нижний угол (штамп)
            stamp_crop = img.crop((
                int(width * STAGE1_STAMP_CROP['left']),
                int(height * STAGE1_STAMP_CROP['top']),
                int(width * STAGE1_STAMP_CROP['right']),
                int(height * STAGE1_STAMP_CROP['bottom'])
            ))

            # Правый верхний угол
            top_right_crop = img.crop((
                int(width * STAGE1_TOP_RIGHT_CROP['left']),
                int(height * STAGE1_TOP_RIGHT_CROP['top']),
                int(width * STAGE1_TOP_RIGHT_CROP['right']),
                int(height * STAGE1_TOP_RIGHT_CROP['bottom'])
            ))

            # Заголовок (верхняя часть)
            header_crop = img.crop((
                int(width * STAGE1_HEADER_CROP['left']),
                int(height * STAGE1_HEADER_CROP['top']),
                int(width * STAGE1_HEADER_CROP['right']),
                int(height * STAGE1_HEADER_CROP['bottom'])
            ))

            # Объединяем в одно изображение для компактности
            combined = Image.new('RGB', (width, int(height * 0.45)))
            combined.paste(header_crop, (0, 0))
            combined.paste(top_right_crop, (int(width * 0.7), int(height * 0.1)))
            combined.paste(stamp_crop, (int(width * 0.7), int(height * 0.25)))

            img_byte_arr = io.BytesIO()
            combined.save(img_byte_arr, format='JPEG', quality=STAGE1_QUALITY)
            base64_image = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
            metadata_images.append({
                'page_number': page_num + 1,
                'image': base64_image
            })

        doc.close()
        logger.info(f"✅ [STAGE 1] Извлечено метаданных с {len(metadata_images)} страниц")
        return metadata_images

    crops = await asyncio.to_thread(_extract_crops)

    # Проверяем лимит страниц (защита от 429 rate limit)
    if len(crops) > STAGE1_MAX_PAGES_PER_REQUEST:
        logger.warning(f"⚠️ [STAGE 1] Слишком много страниц ({len(crops)} > {STAGE1_MAX_PAGES_PER_REQUEST})")
        logger.warning(f"⚠️ [STAGE 1] Разбиваем на батчи по {STAGE1_MAX_PAGES_PER_REQUEST} страниц...")

        all_pages_metadata = []
        for batch_start in range(0, len(crops), STAGE1_MAX_PAGES_PER_REQUEST):
            batch_end = min(batch_start + STAGE1_MAX_PAGES_PER_REQUEST, len(crops))
            batch_crops = crops[batch_start:batch_end]

            logger.info(f"📄 [STAGE 1] Обработка батча страниц {batch_start+1}-{batch_end}...")

            # Формируем запрос для батча
            content = [{
                "type": "text",
                "text": """Проанализируй метаданные строительных чертежей.
Для каждой страницы извлеки:
- Название листа/раздела (из заголовка или штампа)
- Раздел проекта (АР, КР, ИС, ОВ, ВК, ЭС и т.д.)
- Тип чертежа (план, разрез, схема, спецификация)
- Номер листа

ВАЖНО: Обрати особое внимание на:
- Правый нижний угол (штамп документации)
- Правый верхний угол
- Заголовки и названия листов

Верни JSON:
{
  "pages": [
    {"page": 1, "title": "План 1 этажа", "section": "АР", "type": "план", "sheet_number": "АР-01"},
    {"page": 2, "title": "Схема электроснабжения", "section": "ЭС", "type": "схема", "sheet_number": "ЭС-03"}
  ]
}"""
            }]

            # Добавляем изображения батча
            for item in batch_crops:
                content.append({
                    "type": "text",
                    "text": f"\n--- Страница {item['page_number']} ---"
                })
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{item['image']}",
                        "detail": "low"
                    }
                })

            try:
                response = await client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[{"role": "user", "content": content}],
                    temperature=TEMPERATURE,
                    response_format={"type": "json_object"},
                    max_tokens=4000
                )

                data = json.loads(response.choices[0].message.content)
                batch_metadata = data.get('pages', [])
                all_pages_metadata.extend(batch_metadata)
                logger.info(f"✅ [STAGE 1] Батч {batch_start+1}-{batch_end}: извлечено {len(batch_metadata)} метаданных")

            except Exception as e:
                logger.error(f"❌ [STAGE 1] Ошибка в батче {batch_start+1}-{batch_end}: {e}")
                # Fallback для этого батча
                for item in batch_crops:
                    all_pages_metadata.append({
                        "page": item['page_number'],
                        "title": f"Страница {item['page_number']}",
                        "section": "Unknown",
                        "type": "unknown",
                        "sheet_number": f"{item['page_number']}"
                    })

        logger.info(f"✅ [STAGE 1] Извлечено метаданных для {len(all_pages_metadata)} страниц (всего батчей: {(len(crops)-1)//STAGE1_MAX_PAGES_PER_REQUEST + 1})")
        return all_pages_metadata

    # Если страниц мало - отправляем одним запросом (оригинальная логика)
    logger.info(f"🔍 [STAGE 1] Анализ метаданных через Vision API...")

    content = [{
        "type": "text",
        "text": """Проанализируй метаданные строительных чертежей.
Для каждой страницы извлеки:
- Название листа/раздела (из заголовка или штампа)
- Раздел проекта (АР, КР, ИС, ОВ, ВК, ЭС и т.д.)
- Тип чертежа (план, разрез, схема, спецификация)
- Номер листа

ВАЖНО: Обрати особое внимание на:
- Правый нижний угол (штамп документации)
- Правый верхний угол
- Заголовки и названия листов

Верни JSON:
{
  "pages": [
    {"page": 1, "title": "План 1 этажа", "section": "АР", "type": "план", "sheet_number": "АР-01"},
    {"page": 2, "title": "Схема электроснабжения", "section": "ЭС", "type": "схема", "sheet_number": "ЭС-03"}
  ]
}"""
    }]

    # Добавляем изображения метаданных
    for item in crops:
        content.append({
            "type": "text",
            "text": f"\n--- Страница {item['page_number']} ---"
        })
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{item['image']}",
                "detail": "low"
            }
        })

    try:
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": content}],
            temperature=TEMPERATURE,
            response_format={"type": "json_object"},
            max_tokens=4000
        )

        data = json.loads(response.choices[0].message.content)
        pages_metadata = data.get('pages', [])
        logger.info(f"✅ [STAGE 1] Извлечено метаданных для {len(pages_metadata)} страниц")
        return pages_metadata

    except Exception as e:
        logger.error(f"❌ [STAGE 1] Ошибка извлечения метаданных: {e}")
        # Fallback: возвращаем пустые метаданные
        return [{"page": i+1, "title": f"Страница {i+1}", "section": "Unknown", "type": "unknown", "sheet_number": f"{i+1}"}
                for i in range(len(crops))]


async def assess_page_relevance(
    pages_metadata: List[Dict[str, Any]],
    doc_images_low: List[str],
    requirements: List[Dict[str, Any]]
) -> Dict[int, List[int]]:
    """
    Stage 2: Оценка релевантности страниц для каждого требования.
    Возвращает mapping: {requirement_number: [page_numbers]}

    Оптимизировано для gpt-4o-mini: всегда используем Vision API с high-res
    """
    logger.info(f"🔍 [STAGE 2] Оценка релевантности {len(pages_metadata)} страниц для {len(requirements)} требований...")

    # Проверяем, нужно ли разбивать на батчи
    if len(doc_images_low) > STAGE2_MAX_PAGES_PER_REQUEST:
        logger.warning(f"⚠️ [STAGE 2] Много страниц ({len(doc_images_low)} > {STAGE2_MAX_PAGES_PER_REQUEST})")
        logger.warning(f"⚠️ [STAGE 2] Разбиваем на батчи по {STAGE2_MAX_PAGES_PER_REQUEST} страниц...")

        # Обрабатываем батчами
        all_page_mappings = []
        for batch_start in range(0, len(doc_images_low), STAGE2_MAX_PAGES_PER_REQUEST):
            batch_end = min(batch_start + STAGE2_MAX_PAGES_PER_REQUEST, len(doc_images_low))
            batch_images = doc_images_low[batch_start:batch_end]
            batch_metadata = pages_metadata[batch_start:batch_end]

            logger.info(f"📄 [STAGE 2] Обработка батча страниц {batch_start+1}-{batch_end}...")

            # Анализируем батч
            batch_mapping = await _analyze_relevance_batch(batch_metadata, batch_images, requirements, batch_start)
            all_page_mappings.append(batch_mapping)

        # Объединяем результаты всех батчей
        combined_mapping = {}
        for req in requirements:
            req_num = req['number']
            combined_pages = []
            for batch_mapping in all_page_mappings:
                if req_num in batch_mapping:
                    combined_pages.extend(batch_mapping[req_num])
            # Убираем дубликаты и сортируем
            combined_mapping[req_num] = sorted(list(set(combined_pages)))
            logger.info(f"📄 [STAGE 2] Req {req_num}: страницы {combined_mapping[req_num][:5]}{'...' if len(combined_mapping[req_num]) > 5 else ''}")

        logger.info(f"✅ [STAGE 2] Построен mapping для {len(combined_mapping)} требований")
        return combined_mapping

    # Если страниц немного - анализируем одним запросом
    return await _analyze_relevance_batch(pages_metadata, doc_images_low, requirements, 0)


async def _analyze_relevance_batch(
    batch_metadata: List[Dict[str, Any]],
    batch_images: List[str],
    requirements: List[Dict[str, Any]],
    offset: int = 0
) -> Dict[int, List[int]]:
    """
    Вспомогательная функция для анализа батча страниц.
    offset - смещение номеров страниц для корректной нумерации
    """
    # Формируем описание страниц
    pages_description = "\n".join([
        f"Страница {p['page']}: {p.get('title', 'N/A')} [{p.get('section', 'N/A')}] - {p.get('type', 'N/A')}"
        for p in batch_metadata
    ])

    # Формируем список требований
    requirements_text = "\n".join([
        f"{req['number']}. [{req.get('section', 'Общие')}] {req['text'][:200]}..."
        for req in requirements
    ])

    content = [{
        "type": "text",
        "text": f"""Ты эксперт по строительной документации.

Перед тобой {len(batch_images)} страниц проектной документации в ВЫСОКОМ разрешении (gpt-4o-mini оптимизация).
Твоя задача: ТОЧНО определить минимальный набор страниц, содержащих информацию для проверки каждого требования.

МЕТАДАННЫЕ СТРАНИЦ:
{pages_description}

ТРЕБОВАНИЯ ИЗ ТЗ:
{requirements_text}

ВАЖНО при анализе изображений:
- Правый нижний угол (штамп) - номера листов, разделы
- Правый верхний угол - дополнительная маркировка
- Заголовки - названия планов, схем, разрезов

ПРИНЦИПЫ ОТБОРА СТРАНИЦ:
1. Включай ТОЛЬКО страницы с ПРЯМОЙ релевантностью к требованию
2. Оптимально: 3-7 страниц на требование (не более 10)
3. Предпочитай страницы с конкретными данными (планы, схемы, спецификации) над общими листами
4. Исключай дубли и смежные листы с повторяющейся информацией
5. Если требование комплексное - выбирай ключевые листы из каждого раздела

ПРИМЕРЫ:
- "Высота потолков 2.64м" → страницы с планами этажей и разрезами (3-5 листов АР)
- "Паркинг 2-уровневый" → генплан + планы паркинга (2-4 листа)
- "Лифты грузопассажирские" → планы с лифтовыми шахтами + спецификация лифтов (4-6 листов)

Верни JSON:
{{
  "page_mapping": [
    {{"requirement_number": 1, "relevant_pages": [3, 15, 22], "reason": "План 1 этажа, разрез 1-1, спецификация высот"}},
    {{"requirement_number": 2, "relevant_pages": [45, 46], "reason": "Схема вентиляции ОВ, спецификация оборудования"}}
  ]
}}

ВАЖНО: Будь точным и экономным. Лучше 5 релевантных страниц, чем 25 возможно релевантных."""
    }]

    # Добавляем изображения в ВЫСОКОМ качестве (gpt-4o-mini дешевая, не экономим)
    for idx, base64_image in enumerate(batch_images, 1):
        page_num = offset + idx
        content.append({
            "type": "text",
            "text": f"\n--- Страница {page_num} ---"
        })
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{base64_image}",
                "detail": STAGE2_DETAIL  # "high" для точности
            }
        })

    try:
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": content}],
            temperature=TEMPERATURE,
            response_format={"type": "json_object"},
            max_tokens=4000
        )

        data = json.loads(response.choices[0].message.content)
        page_mapping_list = data.get('page_mapping', [])

        # Преобразуем в словарь {requirement_number: [pages]}
        page_mapping = {}
        for item in page_mapping_list:
            req_num = item.get('requirement_number')
            pages = item.get('relevant_pages', [])
            reason = item.get('reason', '')
            page_mapping[req_num] = pages
            logger.info(f"📄 [STAGE 2] Req {req_num}: страницы {pages} ({reason})")

        logger.info(f"✅ [STAGE 2] Построен mapping для {len(page_mapping)} требований")
        return page_mapping

    except Exception as e:
        logger.error(f"❌ [STAGE 2] Ошибка оценки релевантности батча: {e}")
        # Fallback: все страницы из этого батча для всех требований
        logger.warning(f"⚠️ [STAGE 2] Используем fallback для батча - страницы {offset+1}-{offset+len(batch_images)}")
        return {req['number']: list(range(offset + 1, offset + len(batch_images) + 1)) for req in requirements}


@retry(stop=stop_after_attempt(RETRY_MAX_ATTEMPTS), wait=wait_exponential(multiplier=RETRY_WAIT_EXPONENTIAL_MULTIPLIER, min=4, max=RETRY_WAIT_EXPONENTIAL_MAX))
async def find_contradictions(
    pages_metadata: List[Dict[str, Any]],
    doc_content: bytes,
    requirements: List[Dict[str, Any]],
    analyzed_reqs: List['RequirementAnalysis']
) -> str:
    """
    Stage 4: Поиск противоречий в проектной документации.
    Анализирует ключевые страницы из разных разделов и ищет несоответствия.

    Returns: текстовый отчет о найденных противоречиях
    """
    logger.info(f"🔍 [STAGE 4] Начало поиска противоречий в документации...")

    # Группируем страницы по разделам
    sections = {}
    for page_meta in pages_metadata:
        section = page_meta.get('section', 'N/A')
        if section not in sections:
            sections[section] = []
        sections[section].append(page_meta)

    logger.info(f"📊 [STAGE 4] Найдено разделов: {list(sections.keys())}")

    # Отбираем ключевые страницы из каждого раздела
    selected_pages = []
    for section, pages in sections.items():
        # Берем первые N страниц из каждого раздела
        sample = pages[:STAGE4_SAMPLE_PAGES_PER_SECTION]
        selected_pages.extend([p['page'] for p in sample])
        logger.info(f"📄 [STAGE 4] Раздел {section}: выбрано {len(sample)} страниц")

    # Извлекаем выбранные страницы в среднем качестве
    logger.info(f"📄 [STAGE 4] Извлечение {len(selected_pages)} ключевых страниц...")

    def _extract_pages():
        import base64
        from PIL import Image
        import io

        doc = fitz.open(stream=doc_content, filetype="pdf")
        images = []

        for page_num in selected_pages:
            if page_num < 1 or page_num > len(doc):
                continue
            page = doc[page_num - 1]
            pix = page.get_pixmap(dpi=STAGE4_DPI)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=STAGE4_QUALITY)
            base64_image = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
            images.append({'page': page_num, 'image': base64_image})

        doc.close()
        logger.info(f"✅ [STAGE 4] Извлечено {len(images)} страниц")
        return images

    doc_images = await asyncio.to_thread(_extract_pages)

    # Формируем summary проанализированных требований
    requirements_summary = "\n".join([
        f"{r.number}. {r.requirement[:100]}... → {r.status} (уверенность: {r.confidence}%)"
        for r in analyzed_reqs[:20]  # Первые 20 для экономии токенов
    ])

    # Формируем промпт для поиска противоречий
    content = [{
        "type": "text",
        "text": f"""Ты эксперт по строительной документации. Проанализируй проектную документацию на предмет ПРОТИВОРЕЧИЙ и НЕСООТВЕТСТВИЙ.

КОНТЕКСТ ТРЕБОВАНИЙ ИЗ ТЗ (уже проанализированы):
{requirements_summary}

РАЗДЕЛЫ ДОКУМЕНТАЦИИ:
{', '.join(sections.keys())}

ЗАДАЧА:
Найди противоречия между:
1. Разными разделами проекта (АР vs КР, ИС vs ОВ и т.д.)
2. Планами и разрезами одного раздела
3. Текстовыми данными и графическими решениями
4. Требованиями ТЗ и проектными решениями

ТИПЫ ПРОТИВОРЕЧИЙ:
- Размерные несоответствия (высоты, площади, расстояния)
- Расхождения в количестве элементов (лифты, парковки, помещения)
- Конфликты в маркировке и нумерации
- Несоответствия в технических характеристиках
- Противоречия в конструктивных решениях

ВАЖНО:
- Анализируй КОНКРЕТНЫЕ данные с листов (номера, размеры, маркировки)
- Указывай ТОЧНЫЕ ссылки на страницы/листы
- Оценивай критичность каждого противоречия (критично/средне/низко)
- Если противоречий нет - так и укажи

Верни JSON:
{{
  "contradictions": [
    {{
      "type": "Размерное несоответствие",
      "severity": "критично",
      "description": "Высота потолков: АР указывает 2.70м (лист АР-03), КР показывает 2.64м (лист КР-02)",
      "pages": [3, 15],
      "recommendation": "Уточнить проектную высоту с конструкторами"
    }}
  ],
  "summary": "Найдено N противоречий: X критичных, Y средних, Z низких. Требуется согласование разделов АР и КР."
}}

Перед тобой {len(doc_images)} ключевых страниц из разных разделов документации."""
    }]

    # Добавляем изображения
    for img_data in doc_images:
        content.append({
            "type": "text",
            "text": f"\n--- Страница {img_data['page']} ---"
        })
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{img_data['image']}",
                "detail": STAGE4_DETAIL
            }
        })

    try:
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": content}],
            temperature=TEMPERATURE,
            response_format={"type": "json_object"},
            max_tokens=STAGE4_MAX_TOKENS
        )

        result = json.loads(response.choices[0].message.content)
        contradictions = result.get('contradictions', [])
        summary = result.get('summary', 'Анализ завершен')

        logger.info(f"✅ [STAGE 4] Найдено противоречий: {len(contradictions)}")

        # Формируем текстовый отчет
        if not contradictions:
            return "✅ ПРОТИВОРЕЧИЙ НЕ ОБНАРУЖЕНО\n\nПроектная документация не содержит явных противоречий между разделами."

        report = f"🔍 ОТЧЕТ О ПРОТИВОРЕЧИЯХ\n\n{summary}\n\n"
        report += "=" * 80 + "\n\n"

        for idx, contr in enumerate(contradictions, 1):
            severity_emoji = {"критично": "🔴", "средне": "🟡", "низко": "🟢"}.get(contr.get('severity', 'средне'), "⚪")
            report += f"{idx}. {severity_emoji} {contr.get('type', 'Несоответствие').upper()}\n"
            report += f"   Критичность: {contr.get('severity', 'средне')}\n"
            report += f"   Описание: {contr.get('description', 'N/A')}\n"
            report += f"   Страницы: {', '.join(map(str, contr.get('pages', [])))}\n"
            report += f"   Рекомендация: {contr.get('recommendation', 'Требуется уточнение')}\n\n"

        return report

    except Exception as e:
        logger.error(f"❌ [STAGE 4] Ошибка поиска противоречий: {e}")
        return f"⚠️ ОШИБКА АНАЛИЗА ПРОТИВОРЕЧИЙ\n\nНе удалось выполнить анализ: {str(e)}"


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


async def analyze_batch_with_high_detail(
    system_prompt: str,
    doc_content: bytes,
    page_numbers: List[int],
    requirements_batch: List[Dict[str, Any]],
    request: Request
) -> List['RequirementAnalysis']:
    """
    Stage 3: Детальный анализ пакета требований с ВЫСОКИМ разрешением релевантных страниц.
    """
    if await request.is_disconnected():
        logger.warning(f"⚠️ [STAGE 3] Client disconnected")
        return []

    batch_ids = [req['trace_id'] for req in requirements_batch]
    logger.info(f"🔍 [STAGE 3] Анализ {len(requirements_batch)} требований на страницах {page_numbers[:5]}{'...' if len(page_numbers) > 5 else ''}")

    # Проверка лимита страниц (защита от 429 rate limit)
    if len(page_numbers) > STAGE3_MAX_PAGES_PER_REQUEST:
        logger.warning(f"⚠️ [STAGE 3] Слишком много страниц ({len(page_numbers)} > {STAGE3_MAX_PAGES_PER_REQUEST})")
        logger.warning(f"⚠️ [STAGE 3] Разбиваем требования на подгруппы по страницам...")

        # Разбиваем page_numbers на чанки
        all_results = []
        for i in range(0, len(page_numbers), STAGE3_MAX_PAGES_PER_REQUEST):
            chunk_pages = page_numbers[i:i + STAGE3_MAX_PAGES_PER_REQUEST]
            logger.info(f"📄 [STAGE 3] Обработка подгруппы страниц {i+1}-{min(i+STAGE3_MAX_PAGES_PER_REQUEST, len(page_numbers))}")

            # Рекурсивный вызов с меньшим количеством страниц
            chunk_results = await analyze_batch_with_high_detail(
                system_prompt=system_prompt,
                doc_content=doc_content,
                page_numbers=chunk_pages,
                requirements_batch=requirements_batch,
                request=request
            )

            if not chunk_results:
                return []  # Client disconnected

            all_results.extend(chunk_results)

        # Убираем дубликаты по номеру требования
        seen = set()
        unique_results = []
        for result in all_results:
            if result.number not in seen:
                seen.add(result.number)
                unique_results.append(result)

        return unique_results

    # Извлекаем только релевантные страницы в высоком качестве
    logger.info(f"📄 [STAGE 3] Извлечение {len(page_numbers)} страниц в высоком качестве...")

    def _extract_pages():
        import base64
        from PIL import Image
        import io

        doc = fitz.open(stream=doc_content, filetype="pdf")
        images = []

        for page_num in page_numbers:
            if page_num < 1 or page_num > len(doc):
                continue
            page = doc[page_num - 1]  # page_num начинается с 1
            pix = page.get_pixmap(dpi=STAGE3_DPI)  # Высокое качество
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=STAGE3_QUALITY)  # Высокое качество
            base64_image = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
            images.append(base64_image)

        doc.close()
        logger.info(f"✅ [STAGE 3] Извлечено {len(images)} страниц в высоком качестве")
        return images

    doc_images_high = await asyncio.to_thread(_extract_pages)

    # Формируем список требований
    requirements_text = "\n\n".join([
        f"Требование {req['number']} [{req.get('section', 'Общие')}]:\n{req['text']}"
        for req in requirements_batch
    ])

    content = [{
        "type": "text",
        "text": f"""Проанализируй следующие требования из ТЗ и найди для КАЖДОГО требования решение в проектной документации.

{requirements_text}

Верни результат СТРОГО в JSON формате:
{{
  "analyses": [
    {{
      "number": <номер требования>,
      "requirement": "<текст требования>",
      "status": "<Полностью исполнено|Частично исполнено|Не исполнено|Требует уточнения>",
      "confidence": <0-100>,
      "solution_description": "<описание>",
      "reference": "<конкретная ссылка: номер листа, раздел, страница>",
      "discrepancies": "<несоответствия или '-'>",
      "recommendations": "<рекомендации или '-'>"
    }}
  ]
}}

ВАЖНО: Верни анализ для ВСЕХ {len(requirements_batch)} требований в том же порядке!
Изображения в ВЫСОКОМ разрешении - изучай детали, текст, размеры, маркировку."""
    }]

    # Добавляем изображения в высоком качестве
    for idx, base64_image in enumerate(doc_images_high, 1):
        page_num = page_numbers[idx - 1] if idx <= len(page_numbers) else idx
        content.append({
            "type": "text",
            "text": f"\n--- Страница {page_num} ---"
        })
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{base64_image}",
                "detail": STAGE3_DETAIL  # Высокое качество
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
            response_format={"type": "json_object"},  # Принудительный JSON
            max_tokens=STAGE3_MAX_TOKENS
        )

        response_text = response.choices[0].message.content
        refusal = response.choices[0].message.refusal

        # Проверка на None или refusal
        if response_text is None or refusal:
            logger.error(f"❌ [STAGE 3] Model refused to respond!")
            logger.error(f"Refusal message: {refusal}")
            logger.error(f"Finish reason: {response.choices[0].finish_reason}")
            logger.error(f"Requirements in batch: {[req['number'] for req in requirements_batch]}")
            logger.error(f"Requirements text preview: {[req['text'][:100] for req in requirements_batch]}")

            # Если батч больше 1 и включен retry - пробуем по одному
            if STAGE3_RETRY_ON_REFUSAL and len(requirements_batch) > 1:
                logger.warning(f"⚠️ [STAGE 3] Retry: analyzing {len(requirements_batch)} requirements individually...")
                all_results = []
                for single_req in requirements_batch:
                    try:
                        single_result = await analyze_batch_with_high_detail(
                            system_prompt=system_prompt,
                            doc_content=doc_content,
                            page_numbers=page_numbers,
                            requirements_batch=[single_req],
                            request=request
                        )
                        all_results.extend(single_result)
                    except Exception as e:
                        logger.error(f"❌ [STAGE 3] Failed to analyze requirement {single_req['number']}: {e}")
                        all_results.append(RequirementAnalysis(
                            number=single_req['number'],
                            requirement=single_req['text'],
                            status="Требует уточнения",
                            confidence=0,
                            solution_description="Ошибка при индивидуальном анализе",
                            reference="-",
                            discrepancies=str(e),
                            recommendations="Проверьте вручную",
                            section=single_req.get('section'),
                            trace_id=single_req['trace_id']
                        ))
                return all_results

            # Возвращаем заглушки для всех требований
            return [
                RequirementAnalysis(
                    number=req['number'],
                    requirement=req['text'],
                    status="Требует уточнения",
                    confidence=0,
                    solution_description="Модель отказалась анализировать",
                    reference="-",
                    discrepancies=f"Content filter: {refusal or 'Response is None'}",
                    recommendations="Переформулируйте требование или проверьте вручную",
                    section=req.get('section'),
                    trace_id=req['trace_id']
                )
                for req in requirements_batch
            ]

        logger.info(f"📄 [STAGE 3] Response preview: {response_text[:LOG_RESPONSE_PREVIEW_LENGTH]}...")

        # Парсим JSON
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        if json_start != -1 and json_end > json_start:
            json_str = response_text[json_start:json_end]
            data = json.loads(json_str)

            analyses = data.get('analyses', [])
            req_map = {req['number']: req for req in requirements_batch}

            results = []
            for analysis in analyses:
                req_num = analysis.get('number')
                if req_num in req_map:
                    req = req_map[req_num]
                    results.append(RequirementAnalysis(
                        **analysis,
                        section=req.get('section'),
                        trace_id=req['trace_id']
                    ))

            logger.info(f"✅ [STAGE 3] Проанализировано {len(results)}/{len(requirements_batch)} требований")

            # Добавляем заглушки для пропущенных
            if len(results) < len(requirements_batch):
                analyzed_numbers = {r.number for r in results}
                missing = [req['number'] for req in requirements_batch if req['number'] not in analyzed_numbers]
                logger.warning(f"⚠️ [STAGE 3] Пропущены требования: {missing}")
                for req in requirements_batch:
                    if req['number'] not in analyzed_numbers:
                        results.append(RequirementAnalysis(
                            number=req['number'],
                            requirement=req['text'],
                            status="Требует уточнения",
                            confidence=0,
                            solution_description="Не проанализировано",
                            reference="-",
                            discrepancies="Отсутствует в ответе модели",
                            recommendations="Повторите анализ",
                            section=req.get('section'),
                            trace_id=req['trace_id']
                        ))

            results.sort(key=lambda r: r.number)
            return results
        else:
            logger.error(f"❌ [STAGE 3] No JSON in response. Full response: {response_text[:500]}")
            raise ValueError("No JSON found in response")

    except RateLimitError as e:
        error_msg = str(e)
        logger.error(f"❌ [STAGE 3] Rate limit exceeded: {error_msg}")

        # Проверяем, это превышение TPM из-за большого запроса
        if "tokens per min" in error_msg.lower() and len(page_numbers) > 10:
            logger.warning(f"⚠️ [STAGE 3] Превышен лимит токенов из-за {len(page_numbers)} страниц")
            logger.warning(f"⚠️ [STAGE 3] Автоматически разбиваем на меньшие части...")

            # Разбиваем страницы пополам
            mid = len(page_numbers) // 2
            chunk1_pages = page_numbers[:mid]
            chunk2_pages = page_numbers[mid:]

            all_results = []
            for chunk_pages in [chunk1_pages, chunk2_pages]:
                chunk_results = await analyze_batch_with_high_detail(
                    system_prompt=system_prompt,
                    doc_content=doc_content,
                    page_numbers=chunk_pages,
                    requirements_batch=requirements_batch,
                    request=request
                )
                if not chunk_results:
                    return []
                all_results.extend(chunk_results)

            # Убираем дубликаты
            seen = set()
            unique_results = []
            for result in all_results:
                if result.number not in seen:
                    seen.add(result.number)
                    unique_results.append(result)

            return unique_results

        # Обычная 429 ошибка - retry декоратор обработает
        raise

    except Exception as e:
        logger.error(f"❌ [STAGE 3] Ошибка анализа: {e}")
        if 'response_text' in locals() and response_text is not None:
            logger.error(f"Full response text: {response_text[:1000]}")
        else:
            logger.error("Response text is None or not available")
        return [
            RequirementAnalysis(
                number=req['number'],
                requirement=req['text'],
                status="Требует уточнения",
                confidence=0,
                solution_description="Ошибка анализа",
                reference="-",
                discrepancies=str(e),
                recommendations="Повторите анализ",
                section=req.get('section'),
                trace_id=req['trace_id']
            )
            for req in requirements_batch
        ]




# ============================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ТЗ/ТУ
# ============================

@retry(stop=stop_after_attempt(RETRY_MAX_ATTEMPTS), wait=wait_exponential(multiplier=RETRY_WAIT_EXPONENTIAL_MULTIPLIER, min=4, max=RETRY_WAIT_EXPONENTIAL_MAX))
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
            pix = page.get_pixmap(dpi=100)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # Конвертируем в base64
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=70)
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


@retry(stop=stop_after_attempt(RETRY_MAX_ATTEMPTS), wait=wait_exponential(multiplier=RETRY_WAIT_EXPONENTIAL_MULTIPLIER, min=4, max=RETRY_WAIT_EXPONENTIAL_MAX))
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
            return AnalysisResponse(
                stage=stage,
                req_type="ТЗ+ТУ" if check_tu else "ТЗ",
                requirements=[],
                summary="Анализ прерван: клиент отключился во время извлечения текста из ТЗ"
            )

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
            return AnalysisResponse(
                stage=stage,
                req_type="ТЗ+ТУ" if has_tu else "ТЗ",
                requirements=[],
                summary="Анализ прерван: клиент отключился во время сегментации требований"
            )

        requirements = await segment_requirements(tz_text)

        if not requirements:
            raise HTTPException(status_code=400, detail="No requirements extracted from TZ")

        logger.info(f"✅ Extracted {len(requirements)} requirements")

        # ============================================================
        # ЭТАП 2 [STAGE 1]: Извлечение метаданных страниц
        # ============================================================

        logger.info("📋 [STEP 3/7] STAGE 1: Extracting page metadata...")
        pages_metadata = await extract_page_metadata(doc_content, doc_document.filename, max_pages=150)

        # ============================================================
        # ЭТАП 3 [STAGE 2]: Конвертация в низкое качество и оценка релевантности
        # ============================================================

        logger.info("📤 [STEP 4/7] STAGE 2: Converting to low-res and assessing relevance...")
        doc_images_low = await extract_pdf_pages_as_images(
            doc_content, doc_document.filename,
            max_pages=STAGE2_MAX_PAGES, detail=STAGE2_DETAIL, dpi=STAGE2_DPI, quality=STAGE2_QUALITY
        )

        page_mapping = await assess_page_relevance(pages_metadata, doc_images_low, requirements)

        # ============================================================
        # ЭТАП 4: Подготовка system prompt
        # ============================================================

        system_prompt = get_analysis_system_prompt(stage, "ТЗ+ТУ" if has_tu else "ТЗ")

        # ============================================================
        # ЭТАП 5 [STAGE 3]: Группировка и анализ с высоким разрешением
        # ============================================================

        logger.info(f"🔍 [STEP 5/7] STAGE 3: Analyzing with high-resolution images...")
        analyzed_reqs = []

        # Группируем требования по общим страницам для оптимизации
        from collections import defaultdict
        page_to_reqs = defaultdict(list)

        for req in requirements:
            req_pages = page_mapping.get(req['number'], [])
            if not req_pages:  # Fallback - первые 20 страниц
                req_pages = list(range(1, min(21, len(doc_images_low) + 1)))

            pages_key = tuple(sorted(req_pages))
            page_to_reqs[pages_key].append(req)

        logger.info(f"📦 [STAGE 3] Создано {len(page_to_reqs)} групп по общим страницам")

        for group_idx, (pages_key, reqs_group) in enumerate(page_to_reqs.items(), 1):
            if await request.is_disconnected():
                logger.warning(f"⚠️ Client disconnected at group {group_idx}/{len(page_to_reqs)}")
                # Возвращаем частичные результаты
                return AnalysisResponse(
                    stage=stage,
                    req_type="ТЗ+ТУ" if has_tu else "ТЗ",
                    requirements=analyzed_reqs,
                    summary=f"Анализ прерван: клиент отключился после обработки {len(analyzed_reqs)}/{len(requirements)} требований (группа {group_idx}/{len(page_to_reqs)})"
                )

            logger.info(f"📦 [STAGE 3] [{group_idx}/{len(page_to_reqs)}] Analyzing {len(reqs_group)} requirements on {len(pages_key)} pages")

            # Разбиваем на пакеты по N требований если группа большая
            for batch_start in range(0, len(reqs_group), STAGE3_BATCH_SIZE):
                batch = reqs_group[batch_start:batch_start + STAGE3_BATCH_SIZE]

                batch_results = await analyze_batch_with_high_detail(
                    system_prompt=system_prompt,
                    doc_content=doc_content,
                    page_numbers=list(pages_key),
                    requirements_batch=batch,
                    request=request
                )

                if not batch_results:
                    # Клиент отключился во время batch анализа
                    return AnalysisResponse(
                        stage=stage,
                        req_type="ТЗ+ТУ" if has_tu else "ТЗ",
                        requirements=analyzed_reqs,
                        summary=f"Анализ прерван: клиент отключился во время batch анализа. Обработано {len(analyzed_reqs)}/{len(requirements)} требований"
                    )

                analyzed_reqs.extend(batch_results)

        # Сортируем по исходному порядку из ТЗ
        analyzed_reqs.sort(key=lambda r: r.number)

        # ============================================================
        # ЭТАП 5: Генерация сводки
        # ============================================================

        logger.info("📝 Generating summary...")
        if await request.is_disconnected():
            logger.warning("⚠️ Client disconnected before summary")
            # Возвращаем результаты без summary
            return AnalysisResponse(
                stage=stage,
                req_type="ТЗ+ТУ" if has_tu else "ТЗ",
                requirements=analyzed_reqs,
                summary=f"Анализ завершен, но клиент отключился перед генерацией сводки. Проанализировано {len(analyzed_reqs)} требований."
            )

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
        # ЭТАП 6 (опционально): Поиск противоречий
        # ============================================================

        if STAGE4_ENABLED:
            logger.info("🔍 [STEP 6/7] STAGE 4: Поиск противоречий в документации...")
            try:
                contradictions_report = await find_contradictions(
                    pages_metadata=pages_metadata,
                    doc_content=doc_content,
                    requirements=requirements,
                    analyzed_reqs=analyzed_reqs
                )

                # Добавляем отчет о противоречиях к summary
                summary += "\n\n" + "="*80 + "\n\n" + contradictions_report

                logger.info("✅ [STAGE 4] Анализ противоречий завершен")

            except Exception as e:
                logger.error(f"❌ [STAGE 4] Ошибка при поиске противоречий: {e}")
                summary += f"\n\n⚠️ Анализ противоречий не выполнен: {str(e)}"
        else:
            logger.info("⏭️ [STAGE 4] Пропущен (STAGE4_ENABLED=False)")

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
