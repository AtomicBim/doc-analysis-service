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
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential
from openai import RateLimitError

# Отключаем warnings о deprecation
warnings.filterwarnings("ignore", category=DeprecationWarning, module="openai")

import uvicorn
from fastapi import FastAPI, HTTPException, Form, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import AsyncOpenAI
from dotenv import load_dotenv

# Импорт нашего рефакторингового PDF процессора
from pdf_processor import PDFProcessor, PDFBatchProcessor
from progress_tracker import ProgressTracker
from config import (
    # Stage 1
    STAGE1_MAX_PAGES, STAGE1_DPI, STAGE1_QUALITY, STAGE1_MAX_PAGES_PER_REQUEST,
    STAGE1_STAMP_CROP, STAGE1_TOP_RIGHT_CROP, STAGE1_HEADER_CROP, STAGE1_BOTTOM_CENTER_CROP,
    # Stage 2
    STAGE2_MAX_PAGES, STAGE2_DPI, STAGE2_QUALITY, STAGE2_DETAIL, STAGE2_MAX_PAGES_PER_REQUEST,
    # Stage 3
    STAGE3_DPI, STAGE3_QUALITY, STAGE3_DETAIL, STAGE3_BATCH_SIZE, STAGE3_MAX_COMPLETION_TOKENS, STAGE3_RETRY_ON_REFUSAL, STAGE3_MAX_PAGES_PER_REQUEST,
    # Stage 4
    STAGE4_ENABLED, STAGE4_SAMPLE_PAGES_PER_SECTION, STAGE4_DPI, STAGE4_QUALITY, STAGE4_DETAIL, STAGE4_MAX_COMPLETION_TOKENS,
    # Retry
    RETRY_MAX_ATTEMPTS, RETRY_WAIT_EXPONENTIAL_MULTIPLIER, RETRY_WAIT_EXPONENTIAL_MAX,
    # OpenAI
    OPENAI_MODEL,
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


def load_requirements_extraction_prompt() -> str:
    """Загружает промпт для извлечения требований из ТЗ."""
    prompts_dir = Path(__file__).parent.parent / "prompts"
    file_path = prompts_dir / "requirements_extraction_prompt.txt"
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            prompt = f.read().strip()
        logger.info(f"✅ Загружен промпт для извлечения требований")
        return prompt
    except FileNotFoundError:
        logger.error(f"❌ Не найден файл промпта: {file_path}")
        raise FileNotFoundError(f"Файл промпта не найден: {file_path}")


def load_stage_prompts() -> Dict[str, str]:
    """Загружает промпты для всех стадий анализа."""
    prompts_dir = Path(__file__).parent.parent / "prompts"
    stage_prompts: Dict[str, str] = {}
    
    stage_files = {
        "stage1_metadata": "stage1_metadata_extraction_prompt.txt",
        "stage2_relevance": "stage2_page_relevance_prompt.txt",
        "stage3_analysis": "stage3_detailed_analysis_prompt.txt",
        "stage4_contradictions": "stage4_contradictions_prompt.txt",
        "system_prompt_template": "analysis_system_prompt_template.txt"
    }
    
    for key, filename in stage_files.items():
        file_path = prompts_dir / filename
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                stage_prompts[key] = f.read().strip()
            logger.info(f"✅ Загружен промпт {key}")
        except FileNotFoundError:
            logger.error(f"❌ Не найден файл промпта: {file_path}")
            raise FileNotFoundError(f"Файл промпта не найден: {file_path}")
    
    return stage_prompts


# Загружаем промпты при инициализации
PROMPTS = load_prompts()
REQUIREMENTS_EXTRACTION_PROMPT = load_requirements_extraction_prompt()
STAGE_PROMPTS = load_stage_prompts()

# ============================
# PDF PROCESSING ФУНКЦИИ
# ============================

def normalize_sheet_number_to_digit(sheet_num: str) -> str:
    """
    Нормализует номер листа к ТОЛЬКО ЦИФРОВОМУ формату.
    Примеры:
        "АР-01" → "1"
        "КР-03.1" → "3"
        "Лист 26" → "26"
        "5" → "5"
    """
    import re

    if not sheet_num or sheet_num == "N/A":
        return "N/A"

    # Извлекаем все числа из строки
    numbers = re.findall(r'\d+', str(sheet_num))

    if not numbers:
        logger.warning(f"⚠️ Не удалось извлечь цифры из номера листа: '{sheet_num}'")
        return "N/A"

    # Берем ПОСЛЕДНЕЕ число (обычно это номер листа в форматах типа "АР-01")
    digit_only = numbers[-1]

    # Убираем ведущие нули: "01" → "1"
    digit_only = str(int(digit_only))

    logger.debug(f"📋 Нормализация номера листа: '{sheet_num}' → '{digit_only}'")
    return digit_only


def _combine_crops_for_metadata(crops: List[str]) -> str:
    """
    Объединяет 4 crops (header, top_right, bottom_center, stamp) в одно изображение
    для компактного анализа метаданных страницы.
    """
    import base64
    from PIL import Image
    import io

    # Декодируем base64 изображения
    images = []
    for crop_b64 in crops:
        img_data = base64.b64decode(crop_b64)
        img = Image.open(io.BytesIO(img_data))
        images.append(img)

    # Предполагаем, что все изображения имеют одинаковый размер
    # В будущем можно сделать более гибким
    width, height = images[0].size

    # Создаем комбинированное изображение
    combined = Image.new('RGB', (width, int(height * 0.55)))

    # Размещаем crops:
    # - header: верхняя часть (0, 0)
    combined.paste(images[0], (0, 0))

    # - top_right: правый верхний угол
    combined.paste(images[1], (int(width * 0.7), int(height * 0.1)))

    # - bottom_center: центр внизу
    combined.paste(images[2], (int(width * 0.3), int(height * 0.2)))

    # - stamp: правый нижний угол
    combined.paste(images[3], (int(width * 0.7), int(height * 0.3)))

    # Сохраняем как base64
    img_byte_arr = io.BytesIO()
    combined.save(img_byte_arr, format='JPEG', quality=STAGE1_QUALITY)
    return base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')

async def extract_selected_pdf_pages_as_images(
    doc_content: bytes,
    filename: str,
    selected_pages: List[int],
    detail: str = "low",
    dpi: int = 100,
    quality: int = 70
) -> Tuple[List[str], List[int]]:
    """
    Извлекает ТОЛЬКО выбранные страницы PDF как base64-encoded изображения.
    Возвращает кортеж (images, page_numbers) в той же последовательности.

    Теперь использует оптимизированный PDFBatchProcessor для параллельной обработки.
    """
    logger.info(f"📄 [IMG] Извлечение выбранных страниц из {filename}: {selected_pages[:10]}{'...' if len(selected_pages) > 10 else ''} (detail={detail})")

    processor = PDFBatchProcessor(doc_content, filename)
    images = await processor.extract_pages_batch(selected_pages, dpi, quality)

    # Фильтруем пустые результаты (неудачные страницы)
    valid_images = []
    valid_page_nums = []

    for img, page_num in zip(images, selected_pages):
        if img:  # Не пустая строка
            valid_images.append(img)
            valid_page_nums.append(page_num)

    logger.info(f"✅ [IMG] Извлечено {len(valid_images)}/{len(selected_pages)} выбранных страниц")
    return valid_images, valid_page_nums


async def extract_page_metadata(doc_content: bytes, filename: str, max_pages: int = None) -> List[Dict[str, Any]]:
    """
    Stage 1: Извлекает метаданные страниц (штамп, заголовки) через Vision API.
    Фокус на правый нижний угол (штамп), правый верхний, заголовки.
    """
    if max_pages is None:
        max_pages = STAGE1_MAX_PAGES

    logger.info(f"📋 [STAGE 1] Извлечение метаданных из {filename}...")

    def _extract_crops():
        # Определяем области для вырезания
        crop_areas = [
            STAGE1_HEADER_CROP,       # Заголовок
            STAGE1_TOP_RIGHT_CROP,    # Правый верхний угол
            STAGE1_BOTTOM_CENTER_CROP, # Середина внизу
            STAGE1_STAMP_CROP         # Штамп (правый нижний)
        ]

        with PDFProcessor(doc_content, filename) as processor:
            metadata_images = []
            total_pages = min(processor.page_count, max_pages)

            for page_num in range(1, total_pages + 1):  # 1-based
                # Извлекаем все crops для страницы
                crops = processor.extract_page_crops(page_num, crop_areas, STAGE1_DPI, STAGE1_QUALITY)

                if len(crops) == 4:
                    # Объединяем crops в одно изображение для компактности
                    # Это делается в отдельной функции для читаемости
                    combined_base64 = _combine_crops_for_metadata(crops)
                    metadata_images.append({
                        'page_number': page_num,
                        'image': combined_base64
                    })

            logger.info(f"✅ [STAGE 1] Извлечено метаданных с {len(metadata_images)} страниц")
            return metadata_images

    crops = await asyncio.to_thread(_extract_crops)

    # Функция для обработки одного батча с retry
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def process_batch_with_retry(batch_crops: List[Dict], batch_start: int, batch_end: int) -> List[Dict[str, Any]]:
        """Обработка батча страниц с retry при ошибках"""
        content = [{
            "type": "text",
            "text": STAGE_PROMPTS["stage1_metadata"]
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

        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
            max_completion_tokens=4000
        )

        response_text = response.choices[0].message.content
        if not response_text or not response_text.strip():
            raise ValueError(f"Empty response from OpenAI for batch {batch_start}-{batch_end}")

        try:
            data = json.loads(response_text)
            batch_metadata = data.get('pages', [])
            logger.info(f"✅ [STAGE 1] Батч {batch_start}-{batch_end}: извлечено {len(batch_metadata)} метаданных")
            return batch_metadata
        except json.JSONDecodeError as e:
            logger.error(f"❌ [STAGE 1] JSON parse error for batch {batch_start}-{batch_end}: {e}")
            logger.error(f"Response preview: {response_text[:200]}...")
            raise

    # Проверяем лимит страниц (защита от 429 rate limit)
    if len(crops) > STAGE1_MAX_PAGES_PER_REQUEST:
        logger.warning(f"⚠️ [STAGE 1] Слишком много страниц ({len(crops)} > {STAGE1_MAX_PAGES_PER_REQUEST})")
        logger.warning(f"⚠️ [STAGE 1] Разбиваем на батчи по {STAGE1_MAX_PAGES_PER_REQUEST} страниц...")

        all_pages_metadata = []
        for batch_start in range(0, len(crops), STAGE1_MAX_PAGES_PER_REQUEST):
            batch_end = min(batch_start + STAGE1_MAX_PAGES_PER_REQUEST, len(crops))
            batch_crops = crops[batch_start:batch_end]

            logger.info(f"📄 [STAGE 1] Обработка батча страниц {batch_start+1}-{batch_end}...")

            try:
                # Используем функцию с retry
                batch_metadata = await process_batch_with_retry(batch_crops, batch_start+1, batch_end)
                all_pages_metadata.extend(batch_metadata)

            except Exception as e:
                logger.error(f"❌ [STAGE 1] Все попытки для батча {batch_start+1}-{batch_end} провалились: {e}")
                # Fallback для этого батча
                logger.warning(f"⚠️ [STAGE 1] Используем fallback для батча {batch_start+1}-{batch_end}")
                for item in batch_crops:
                    all_pages_metadata.append({
                        "page": item['page_number'],
                        "title": f"Страница {item['page_number']}",
                        "section": "Unknown",
                        "type": "unknown",
                        "sheet_number": f"{item['page_number']}",
                        "sheet_number_validation": {
                            "matches": False,
                            "found_in": ["stamp", "bottom_center", "top_right"],
                            "values": ["N/A", "N/A", "N/A"]
                        }
                    })

        logger.info(f"✅ [STAGE 1] Извлечено метаданных для {len(all_pages_metadata)} страниц (батчи по {STAGE1_MAX_PAGES_PER_REQUEST})")
        return all_pages_metadata

    # Если страниц мало - отправляем одним запросом (оригинальная логика)
    logger.info(f"🔍 [STAGE 1] Анализ метаданных через Vision API...")

    try:
        # Используем функцию с retry для одиночного запроса
        pages_metadata = await process_batch_with_retry(crops, 1, len(crops))
        logger.info(f"✅ [STAGE 1] Извлечено метаданных для {len(pages_metadata)} страниц")
        return pages_metadata

    except Exception as e:
        logger.error(f"❌ [STAGE 1] Все попытки извлечения метаданных провалились: {e}")
        # Fallback: возвращаем пустые метаданные
        logger.warning(f"⚠️ [STAGE 1] Используем fallback для всех {len(crops)} страниц")
        return [{
            "page": i+1,
            "title": f"Страница {i+1}",
            "section": "Unknown",
            "type": "unknown",
            "sheet_number": f"{i+1}",
            "sheet_number_validation": {
                "matches": False,
                "found_in": ["stamp", "bottom_center", "top_right"],
                "values": ["N/A", "N/A", "N/A"]
            }
        } for i in range(len(crops))]


async def assess_page_relevance(
    pages_metadata: List[Dict[str, Any]],
    doc_images_low: List[str],
    requirements: List[Dict[str, Any]],
    page_numbers: Optional[List[int]] = None
) -> Dict[int, List[int]]:
    """
    Stage 2: Оценка релевантности страниц для каждого требования.
    Возвращает mapping: {requirement_number: [page_numbers]}

    Оптимизировано для gpt-5-mini: всегда используем Vision API с high-res
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
            batch_page_numbers = page_numbers[batch_start:batch_end] if page_numbers else list(range(batch_start + 1, batch_end + 1))

            logger.info(f"📄 [STAGE 2] Обработка батча страниц {batch_start+1}-{batch_end}...")

            # Анализируем батч
            batch_mapping = await _analyze_relevance_batch(batch_metadata, batch_images, requirements, 0, batch_page_numbers)
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
    return await _analyze_relevance_batch(pages_metadata, doc_images_low, requirements, 0, page_numbers or list(range(1, len(doc_images_low)+1)))


async def _analyze_relevance_batch(
    batch_metadata: List[Dict[str, Any]],
    batch_images: List[str],
    requirements: List[Dict[str, Any]],
    offset: int = 0,
    page_numbers: Optional[List[int]] = None
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

    # Используем загруженный промпт с подстановкой переменных
    prompt_text = STAGE_PROMPTS["stage2_relevance"].format(
        page_count=len(batch_images),
        pages_description=pages_description,
        requirements_text=requirements_text
    )

    content = [{
        "type": "text",
        "text": prompt_text
    }]

    # Добавляем изображения в ВЫСОКОМ качестве (gpt-5-mini дешевая, не экономим)
    for idx, base64_image in enumerate(batch_images, 1):
        page_num = (page_numbers[idx - 1] if page_numbers and idx - 1 < len(page_numbers) else (offset + idx))
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
            response_format={"type": "json_object"},
            max_completion_tokens=4000
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


# ============================
# TEXT PREFILTER FOR STAGE 2
# ============================

def _extract_page_texts_quick(doc_content: bytes, max_pages: int = 200) -> List[str]:
    """Быстро извлекает текст по страницам без OCR (для префильтра)."""
    with PDFProcessor(doc_content, "temp.pdf") as processor:
        return processor.extract_text_pages(max_pages)


def _simple_candidate_pages(requirements: List[Dict[str, Any]], page_texts: List[str], per_req: int = 7, cap_total: int = 30) -> List[int]:
    """Простой текстовый префильтр: выбирает top-k страниц для каждого требования по совпадению ключевых слов."""
    import re
    candidates: List[int] = []
    # Очень простой tokenizer
    def toks(s: str) -> List[str]:
        return re.findall(r"[A-Za-zА-Яа-яЁё0-9_-]{2,}", (s or "").lower())

    page_tokens = [toks(t) for t in page_texts]

    for req in requirements:
        words = toks(req.get('text', ''))
        if not words:
            continue
        scores: List[Tuple[int, int]] = []  # (page_index, score)
        word_set = set(words)
        for idx, p_tokens in enumerate(page_tokens):
            if not p_tokens:
                continue
            score = sum(1 for w in p_tokens if w in word_set)
            if score:
                scores.append((idx, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        top = [i for (i, _) in scores[:per_req]]
        candidates.extend(top)

    # Уникальные, отсортированные, ограниченные по количеству
    uniq = sorted(list({i for i in candidates}))
    if not uniq:
        # fallback: первые 20 страниц
        uniq = list(range(0, min(20, len(page_texts))))
    return [i + 1 for i in uniq[:cap_total]]  # 1-based


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

    # Используем новый PDFBatchProcessor для параллельного извлечения
    processor = PDFBatchProcessor(doc_content, "contradictions_analysis.pdf")
    image_bases = await processor.extract_pages_batch(selected_pages, STAGE4_DPI, STAGE4_QUALITY)

    doc_images = []
    for page_num, base64_image in zip(selected_pages, image_bases):
        if base64_image:  # Только успешные извлечения
            doc_images.append({'page': page_num, 'image': base64_image})

    logger.info(f"✅ [STAGE 4] Извлечено {len(doc_images)} страниц")

    # Формируем summary проанализированных требований
    requirements_summary = "\n".join([
        f"{r.number}. {r.requirement[:100]}... → {r.status} (уверенность: {r.confidence}%)"
        for r in analyzed_reqs[:20]  # Первые 20 для экономии токенов
    ])

    # Используем загруженный промпт
    prompt_text = STAGE_PROMPTS["stage4_contradictions"].format(
        requirements_summary=requirements_summary,
        sections=', '.join(sections.keys()),
        page_count=len(doc_images)
    )

    # Формируем промпт для поиска противоречий
    content = [{
        "type": "text",
        "text": prompt_text
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
            response_format={"type": "json_object"},
            max_completion_tokens=STAGE4_MAX_COMPLETION_TOKENS
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


def normalize_status_confidence(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Нормализует несогласованности между status и confidence.
    
    Правила:
    - "Полностью исполнено" → confidence >= 70%
    - "Частично исполнено" → confidence 40-80%
    - "Не исполнено" → confidence >= 60% (уверены, что НЕ исполнено)
    - "Требует уточнения" → confidence <= 40%
    """
    status = analysis.get('status', '')
    confidence = analysis.get('confidence', 0)
    
    # Нормализуем confidence в диапазон 0-100
    if confidence < 0:
        confidence = 0
    elif confidence > 100:
        confidence = 100
    
    # Проверяем и корректируем несогласованности
    if status == "Полностью исполнено":
        if confidence < 70:
            # Низкая уверенность для "полностью исполнено" - меняем статус
            logger.warning(f"⚠️ Несогласованность: status='Полностью исполнено', confidence={confidence}. Исправляем статус на 'Частично исполнено'")
            analysis['status'] = "Частично исполнено"
            
    elif status == "Требует уточнения":
        if confidence > 40:
            # Высокая уверенность для "требует уточнения" - корректируем
            logger.warning(f"⚠️ Несогласованность: status='Требует уточнения', confidence={confidence}. Снижаем confidence до 30%")
            analysis['confidence'] = 30
            
    elif status == "Частично исполнено":
        # Приводим к разумным границам
        if confidence < 40:
            analysis['confidence'] = 40
        elif confidence > 80:
            # Слишком высокая уверенность - возможно "полностью исполнено"
            logger.warning(f"⚠️ Несогласованность: status='Частично исполнено', confidence={confidence}. Меняем на 'Полностью исполнено'")
            analysis['status'] = "Полностью исполнено"
            
    elif status == "Не исполнено":
        # Для "не исполнено" confidence показывает уверенность в отсутствии
        if confidence < 50:
            # Низкая уверенность - возможно требует уточнения
            logger.warning(f"⚠️ Несогласованность: status='Не исполнено', confidence={confidence}. Меняем на 'Требует уточнения'")
            analysis['status'] = "Требует уточнения"
            analysis['confidence'] = confidence
    
    return analysis


def get_analysis_system_prompt(stage: str, req_type: str) -> str:
    """
    Возвращает system prompt для анализа документации.
    """
    stage_prompt = PROMPTS.get(stage, PROMPTS["ФЭ"])
    # В system_prompt_template есть необрамленные фигурные скобки (JSON-примеры),
    # поэтому используем безопасную замену только плейсхолдера {req_type}.
    system_template_raw = STAGE_PROMPTS["system_prompt_template"]
    system_template = system_template_raw.replace("{req_type}", req_type)

    return f"{stage_prompt}\n\n{system_template}"


async def analyze_batch_with_high_detail(
    system_prompt: str,
    doc_content: bytes,
    page_numbers: List[int],
    requirements_batch: List[Dict[str, Any]],
    request: Request,
    pages_metadata: Optional[List[Dict[str, Any]]] = None
) -> List['RequirementAnalysis']:
    """
    Stage 3: Детальный анализ пакета требований с ВЫСОКИМ разрешением релевантных страниц.
    
    Args:
        pages_metadata: Метаданные страниц с номерами листов из Stage 1
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
                request=request,
                pages_metadata=pages_metadata
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

    # Используем PDFBatchProcessor для параллельного извлечения в высоком качестве
    processor = PDFBatchProcessor(doc_content, "stage3_analysis.pdf")
    doc_images_high = await processor.extract_pages_batch(
        page_numbers, STAGE3_DPI, STAGE3_QUALITY, max_concurrent=3  # Меньше одновременных для высокого качества
    )

    logger.info(f"✅ [STAGE 3] Извлечено {len([img for img in doc_images_high if img])} страниц в высоком качестве")

    # Формируем список требований
    requirements_text = "\n\n".join([
        f"Требование {req['number']} [{req.get('section', 'Общие')}]:\n{req['text']}"
        for req in requirements_batch
    ])

    # Создаем mapping PDF страница → Номер листа проекта
    page_to_sheet_mapping = {}
    if pages_metadata:
        for page_meta in pages_metadata:
            pdf_page = page_meta.get('page')
            sheet_num = page_meta.get('sheet_number', f"Стр.{pdf_page}")
            if pdf_page:
                page_to_sheet_mapping[pdf_page] = sheet_num
    
    # Формируем список доступных страниц с номерами листов
    if page_to_sheet_mapping:
        available_pages_list = []
        for page_num in page_numbers:
            sheet_num = page_to_sheet_mapping.get(page_num, f"Стр.{page_num}")
            available_pages_list.append(f"PDF стр.{page_num} (Лист {sheet_num})")
        available_pages_str = ", ".join(available_pages_list)
        logger.info(f"📄 [STAGE 3] Доступные листы: {available_pages_str[:200]}...")
    else:
        # Fallback если нет метаданных
        available_pages_str = ", ".join(map(str, page_numbers))
        logger.warning(f"⚠️ [STAGE 3] Нет метаданных о листах, используем PDF страницы")

    # Используем загруженный промпт
    prompt_text = STAGE_PROMPTS["stage3_analysis"].format(
        requirements_text=requirements_text,
        requirements_count=len(requirements_batch),
        available_pages=available_pages_str,
        page_count=len(page_numbers)
    )

    content = [{
        "type": "text",
        "text": prompt_text
    }]

    # Добавляем изображения в высоком качестве с номерами листов
    for idx, base64_image in enumerate(doc_images_high, 1):
        page_num = page_numbers[idx - 1] if idx <= len(page_numbers) else idx
        
        # Получаем номер листа проекта для подписи
        if page_to_sheet_mapping and page_num in page_to_sheet_mapping:
            sheet_num = page_to_sheet_mapping[page_num]
            page_label = f"PDF стр.{page_num} (Лист {sheet_num})"
        else:
            page_label = f"Страница {page_num}"
        
        content.append({
            "type": "text",
            "text": f"\n--- {page_label} ---"
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
            response_format={"type": "json_object"},  # Принудительный JSON
            max_completion_tokens=STAGE3_MAX_COMPLETION_TOKENS
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
                            request=request,
                            pages_metadata=pages_metadata
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
                            section=single_req.get('section')
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
                    section=req.get('section')
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

            # Поддержка двух форматов: { analyses: [...] } ИЛИ одиночный объект анализа
            if 'analyses' in data:
                analyses = data.get('analyses', [])
            else:
                # Пытаемся интерпретировать как единичный объект анализа
                analyses = [data]

            # Нормализуем тип: если analyses — словарь, оборачиваем его в список
            if isinstance(analyses, dict):
                analyses = [analyses]
            req_map = {req['number']: req for req in requirements_batch}

            results = []
            for analysis in analyses:
                req_num = analysis.get('number')
                if req_num in req_map:
                    req = req_map[req_num]
                    # Нормализуем несогласованности между status и confidence
                    normalized_analysis = normalize_status_confidence(analysis)

                    # 🔧 КРИТИЧЕСКИ ВАЖНО: Валидация и нормализация reference к ТОЛЬКО ЦИФРОВОМУ формату
                    reference = normalized_analysis.get('reference', '-')
                    if reference and reference != "-":
                        # Нормализуем reference к цифровому формату если содержит букву
                        import re
                        if re.search(r'[а-яА-ЯёЁa-zA-Z]', reference):
                            logger.warning(f"⚠️ [STAGE 3] Req {req_num}: reference содержит буквы: '{reference}'")
                            normalized_ref = normalize_sheet_number_to_digit(reference)
                            normalized_analysis['reference'] = normalized_ref
                            logger.info(f"📋 [STAGE 3] Req {req_num}: нормализовано reference '{reference}' → '{normalized_ref}'")

                    results.append(RequirementAnalysis(
                        **normalized_analysis,
                        section=req.get('section')
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
                            section=req.get('section')
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
                    request=request,
                    pages_metadata=pages_metadata
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
                section=req.get('section')
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

    with PDFProcessor(content, filename) as processor:
        # Mixed-mode: постранично
        for page_index in range(processor.page_count):
            page = processor.get_page(page_index + 1)  # 1-based
            page_text = page.get_text() or ""

            if page_text.strip():
                text += page_text + "\n\n"
                continue

            # OCR только для пустых по тексту страниц
            logger.info(f"📄 OCR страницы {page_index + 1}/{processor.page_count} из {filename}")

            # Используем новый процессор для извлечения изображения
            images = processor.extract_pages_as_images([page_index + 1], 100, 70)
            if not images:
                continue

            base64_image = images[0]

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
                max_completion_tokens=4000
            )
            page_text = response.choices[0].message.content or ""
            text += f"\n\n--- Страница {page_index + 1} ---\n\n{page_text}"

    logger.info(f"✅ Извлечен текст из PDF {filename}, символов: {len(text)}")

    if not text.strip():
        logger.error(f"❌ Не удалось извлечь текст из {filename}")
        return "[Документ пуст или не удалось распознать текст]"

    return text.strip()


async def extract_text_from_docx(content: bytes, filename: str) -> str:
    """Извлекает текст из DOCX, включая таблицы."""
    try:
        from docx import Document as DocxDocument
    except Exception:
        logger.error("python-docx не установлен")
        return ""

    import io
    text_parts: List[str] = []
    docx_stream = io.BytesIO(content)
    doc = DocxDocument(docx_stream)

    # Параграфы
    for p in doc.paragraphs:
        if p.text and p.text.strip():
            text_parts.append(p.text.strip())

    # Таблицы
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                text_parts.append(" | ".join(cells))

    result = "\n".join(text_parts)
    logger.info(f"✅ Извлечен текст из DOCX {filename}, символов: {len(result)}")
    return result


async def extract_text_from_any(content: bytes, filename: str) -> str:
    """Определяет тип (docx/pdf) и извлекает текст соответствующим способом."""
    lower = (filename or "").lower()
    if lower.endswith('.docx'):
        return await extract_text_from_docx(content, filename)
    # default: PDF
    return await extract_text_from_pdf(content, filename)


@retry(stop=stop_after_attempt(RETRY_MAX_ATTEMPTS), wait=wait_exponential(multiplier=RETRY_WAIT_EXPONENTIAL_MULTIPLIER, min=4, max=RETRY_WAIT_EXPONENTIAL_MAX))
async def segment_requirements(tz_text: str) -> List[Dict[str, Any]]:
    """Сегментирует ТЗ на отдельные требования используя GPT."""
    # Формируем промпт из загруженного шаблона + текст ТЗ
    prompt = f"""{REQUIREMENTS_EXTRACTION_PROMPT}

Текст ТЗ:
{tz_text[:10000]}"""  # Ограничиваем до 10000 символов

    response = await client.chat.completions.create(
        model=OPENAI_MODEL,  # Используем модель из конфига
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )

    try:
        response_text = response.choices[0].message.content
        logger.info(f"📄 GPT response preview: {response_text[:500]}...")
        
        data = json.loads(response_text)
        logger.info(f"📊 Parsed JSON keys: {list(data.keys())}")
        
        requirements = data.get("requirements", [])
        
        if not requirements:
            logger.warning(f"⚠️ Пустой список требований! Полный ответ GPT: {response_text}")
        
        logger.info(f"✅ Извлечено {len(requirements)} требований")
        return requirements
    except json.JSONDecodeError as e:
        logger.error(f"❌ Failed to parse requirements JSON: {e}")
        logger.error(f"❌ Response text: {response.choices[0].message.content}")
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
    evidence_text: Optional[str] = None  # Конкретный текст с листа для поиска
    discrepancies: str
    section: Optional[str] = None


class AnalysisResponse(BaseModel):
    """Ответ с результатами анализа"""
    stage: str
    req_type: str
    requirements: List[RequirementAnalysis]
    summary: str
    sheet_to_pdf_mapping: Optional[Dict[str, int]] = {}  # Mapping: sheet_number → pdf_page_number


# ============================
# ГЛОБАЛЬНОЕ СОСТОЯНИЕ АНАЛИЗА
# ============================

analysis_status = {
    "current_stage": None,
    "progress": 0,
    "stage_name": "",
    "total_stages": 3,
    "start_time": None,
    "is_running": False
}

def update_analysis_status(stage_num: int, stage_name: str, progress: int):
    """Обновляет глобальный статус анализа"""
    analysis_status.update({
        "current_stage": stage_num,
        "progress": progress,
        "stage_name": stage_name,
        "is_running": True
    })
    logger.info(f"📊 Status updated: Stage {stage_num}/3 - {stage_name} - {progress}%")

def reset_analysis_status():
    """Сбрасывает статус анализа"""
    analysis_status.update({
        "current_stage": None,
        "progress": 0,
        "stage_name": "",
        "is_running": False,
        "start_time": None
    })

# After analysis_status definition
extraction_status = {
    "current_stage": None,
    "progress": 0,
    "stage_name": "",
    "total_stages": 2,
    "start_time": None,
    "is_running": False
}

def update_extraction_status(stage_num: int, stage_name: str, progress: int):
    extraction_status.update({
        "current_stage": stage_num,
        "progress": progress,
        "stage_name": stage_name,
        "is_running": True
    })
    logger.info(f"📊 Extraction status updated: Stage {stage_num}/2 - {stage_name} - {progress}%")

def reset_extraction_status():
    extraction_status.update({
        "current_stage": None,
        "progress": 0,
        "stage_name": "",
        "is_running": False,
        "start_time": None
    })

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
        "architecture": "Two-step: 1) Extract requirements from TZ, 2) Analyze project",
        "provider": "openai",
        "model": OPENAI_MODEL,
        "max_file_size_mb": MAX_FILE_SIZE_MB
    }


@app.get("/status")
async def get_analysis_status():
    """Получить текущий статус анализа"""
    return analysis_status

@app.get("/extraction_status")
async def get_extraction_status():
    return extraction_status


@app.post("/extract_requirements")
async def extract_requirements_endpoint(
    request: Request,
    tz_document: UploadFile = File(...)
):
    """
    Шаг 1: Извлечение требований из ТЗ.
    Поддерживает PDF (текст и изображения) и DOCX.
    
    Returns:
        List of requirements with structure:
        [
            {
                "number": 1,
                "text": "requirement text",
                "section": "category",
                "trace_id": "req-1",
                "selected": true  # по умолчанию все выбраны
            }
        ]
    """
    try:
        if await request.is_disconnected():
            logger.warning("⚠️ Client disconnected before extraction started.")
            raise HTTPException(status_code=499, detail="Client disconnected")
        
        # Сбрасываем и инициализируем статус
        reset_extraction_status()
        update_extraction_status(1, "Подготовка документа", 5)
        
        logger.info(f"📋 [STEP 1] Извлечение требований из {tz_document.filename}")
        
        # Проверка размера файла
        file_size = await _get_file_size(tz_document)
        if file_size > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Файл {tz_document.filename} слишком большой ({file_size / 1024 / 1024:.2f} MB). Максимум: {MAX_FILE_SIZE_MB} MB"
            )
        
        # Читаем содержимое
        await tz_document.seek(0)
        tz_content = await tz_document.read()
        
        logger.info(f"📊 File size: {len(tz_content) / 1024:.1f} KB")
        update_extraction_status(1, "Извлечение текста из документа", 20)
        
        # Извлекаем текст из документа
        logger.info("📄 Extracting text from TZ document...")
        if await request.is_disconnected():
            logger.warning("⚠️ Client disconnected during text extraction")
            raise HTTPException(status_code=499, detail="Client disconnected")
        
        tz_text = await extract_text_from_any(tz_content, tz_document.filename)
        update_extraction_status(1, "Текст успешно извлечён", 50)
        
        # Сегментируем требования
        logger.info("✂️ Segmenting requirements...")
        update_extraction_status(2, "Сегментация требований", 60)
        
        if await request.is_disconnected():
            logger.warning("⚠️ Client disconnected during segmentation")
            raise HTTPException(status_code=499, detail="Client disconnected")
        
        requirements = await segment_requirements(tz_text)
        update_extraction_status(2, "Сегментация завершена", 90)
        
        if not requirements:
            raise HTTPException(status_code=400, detail="No requirements extracted from TZ")
        
        # Добавляем поле selected=true для всех требований по умолчанию
        for req in requirements:
            req['selected'] = True
        
        logger.info(f"✅ Successfully extracted {len(requirements)} requirements")
        update_extraction_status(2, f"Извлечено {len(requirements)} требований", 100)
        
        return {
            "success": True,
            "total_requirements": len(requirements),
            "requirements": requirements
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error extracting requirements: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка извлечения требований: {str(e)}")


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_documentation(
    request: Request,
    stage: str = Form(...),
    requirements_json: str = Form(...),  # JSON string с требованиями из шага 1
    doc_document: UploadFile = File(...)
):
    """
    Шаг 2: Анализ проектной документации по готовым требованиям.
    
    Args:
        stage: Стадия проекта (ГК, ФЭ, ЭП)
        requirements_json: JSON string с требованиями из шага 1
        doc_document: Файл проектной документации (PDF)
    """
    try:
        # Проверяем, не отключился ли клиент
        if await request.is_disconnected():
            logger.warning("⚠️ Client disconnected before analysis started. Aborting.")
            raise HTTPException(status_code=499, detail="Client disconnected")

        logger.info(f"📋 [STEP 2] Анализ проектной документации. Стадия: {stage}")

        # Сбрасываем статус и начинаем анализ
        reset_analysis_status()

        # ============================================================
        # ЭТАП 1: Парсинг требований из JSON
        # ============================================================

        try:
            requirements = json.loads(requirements_json)
            logger.info(f"📋 Получено {len(requirements)} требований из шага 1")
            update_analysis_status(1, "Подготовка данных", 5)
            
            # Фильтруем только выбранные требования (selected=true)
            selected_requirements = [req for req in requirements if req.get('selected', True)]
            logger.info(f"✅ Выбрано {len(selected_requirements)} требований для анализа")
            
            if not selected_requirements:
                raise HTTPException(status_code=400, detail="No requirements selected for analysis")
            
            requirements = selected_requirements
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to parse requirements JSON: {e}")
            raise HTTPException(status_code=400, detail="Invalid requirements JSON format")

        # ============================================================
        # ЭТАП 2: Проверка файла проектной документации
        # ============================================================
        
        # Проверка размера файла
        file_size = await _get_file_size(doc_document)
        if file_size > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Файл {doc_document.filename} слишком большой ({file_size / 1024 / 1024:.2f} MB). Максимум: {MAX_FILE_SIZE_MB} MB"
            )

        # Read contents
        await doc_document.seek(0)
        doc_content = await doc_document.read()

        logger.info(f"📊 File size - DOC: {len(doc_content) / 1024:.1f} KB")

        # ============================================================
        # ЭТАП 3 [STAGE 1]: Извлечение метаданных страниц
        # ============================================================

        logger.info("📋 [STEP 1/3] STAGE 1: Extracting page metadata...")
        pages_metadata = await extract_page_metadata(doc_content, doc_document.filename, max_pages=150)

        # 🔧 КРИТИЧЕСКИ ВАЖНО: Нормализуем номера листов к ТОЛЬКО ЦИФРОВОМУ формату
        logger.info("📋 [STAGE 1] Нормализация номеров листов к цифровому формату...")
        for page_meta in pages_metadata:
            original_sheet_num = page_meta.get('sheet_number')
            if original_sheet_num and original_sheet_num != "N/A":
                normalized_sheet_num = normalize_sheet_number_to_digit(original_sheet_num)
                page_meta['sheet_number'] = normalized_sheet_num
                if normalized_sheet_num != original_sheet_num:
                    logger.info(f"📋 Нормализовано: стр.{page_meta.get('page')} '{original_sheet_num}' → '{normalized_sheet_num}'")

        logger.info(f"✅ [STAGE 1] Нормализация завершена. Все номера листов теперь в цифровом формате.")
        update_analysis_status(1, "Извлечение метаданных", 33)

        # Создаем mapping: sheet_number → pdf_page_number для навигации
        sheet_to_pdf_mapping = {}
        for page_meta in pages_metadata:
            pdf_page = page_meta.get('page')
            sheet_num = page_meta.get('sheet_number', str(pdf_page))

            # Пропускаем невалидные номера
            if not sheet_num or sheet_num == "N/A":
                continue

            # Нормализуем номер листа для надежного поиска
            sheet_num_normalized = str(sheet_num).strip()

            # Проверяем дубликаты и предупреждаем
            if sheet_num_normalized in sheet_to_pdf_mapping:
                logger.warning(f"⚠️ [STAGE 1] Дубликат номера листа '{sheet_num_normalized}': PDF страницы {sheet_to_pdf_mapping[sheet_num_normalized]} и {pdf_page}")
                # Сохраняем первое вхождение (обычно оно корректное)
                continue

            sheet_to_pdf_mapping[sheet_num_normalized] = pdf_page

            # Добавляем альтернативные варианты записи для надежности
            # Например: "АР-01" → также доступен как "АР-1", "ар-01", "АР01"
            alternatives = []

            # Вариант без нулей: "АР-01" → "АР-1"
            if '-' in sheet_num_normalized:
                parts = sheet_num_normalized.split('-')
                if len(parts) == 2 and parts[1].isdigit():
                    alternatives.append(f"{parts[0]}-{int(parts[1])}")

            # Вариант без дефиса: "АР-01" → "АР01"
            alternatives.append(sheet_num_normalized.replace('-', ''))
            alternatives.append(sheet_num_normalized.replace('–', ''))  # em-dash
            alternatives.append(sheet_num_normalized.replace('—', ''))  # en-dash

            # Вариант в нижнем регистре
            alternatives.append(sheet_num_normalized.lower())

            # Добавляем все альтернативы
            for alt in alternatives:
                if alt and alt != sheet_num_normalized and alt not in sheet_to_pdf_mapping:
                    sheet_to_pdf_mapping[alt] = pdf_page

        logger.info(f"📊 [STAGE 1] Создан mapping листов: {len(sheet_to_pdf_mapping)} вариантов для {len(pages_metadata)} страниц")
        logger.info(f"📊 [STAGE 1] Примеры: {list(sheet_to_pdf_mapping.items())[:10]}...")


        # ============================================================
        # ЭТАП 2 [STAGE 2]: Конвертация в низкое качество и оценка релевантности
        # ============================================================

        logger.info("📤 [STEP 2/3] STAGE 2: Converting to low-res and assessing relevance...")
        update_analysis_status(2, "Префильтр страниц по тексту", 40)

        # Текстовый префильтр страниц
        page_texts_quick = _extract_page_texts_quick(doc_content, max_pages=STAGE2_MAX_PAGES)
        candidate_pages = _simple_candidate_pages(requirements, page_texts_quick, per_req=7, cap_total=30)
        logger.info(f"📄 [STAGE 2] Текстовый префильтр выбрал страницы: {candidate_pages[:10]}{'...' if len(candidate_pages) > 10 else ''}")

        update_analysis_status(2, "Извлечение выбранных страниц", 50)

        # Извлекаем только выбранные страницы в low-res
        doc_images_low, page_numbers_kept = await extract_selected_pdf_pages_as_images(
            doc_content, doc_document.filename, selected_pages=candidate_pages,
            detail=STAGE2_DETAIL, dpi=STAGE2_DPI, quality=STAGE2_QUALITY
        )

        update_analysis_status(2, "Оценка релевантности страниц", 60)

        page_mapping = await assess_page_relevance(pages_metadata, doc_images_low, requirements, page_numbers=page_numbers_kept)
        update_analysis_status(2, "Релевантность определена", 66)

        # ============================================================
        # ЭТАП 5: Подготовка system prompt
        # ============================================================

        system_prompt = get_analysis_system_prompt(stage, "ТЗ")

        # ============================================================
        # ЭТАП 6 [STAGE 3]: Группировка и анализ с высоким разрешением
        # ============================================================

        logger.info(f"🔍 [STEP 3/3] STAGE 3: Analyzing with high-resolution images...")
        update_analysis_status(3, "Детальный анализ требований", 70)
        analyzed_reqs = []

        # Группируем требования по общим страницам для оптимизации
        from collections import defaultdict
        page_to_reqs = defaultdict(list)

        for req in requirements:
            req_pages = page_mapping.get(req['number'], [])
            if not req_pages:  # Fallback - первые 20 страниц
                req_pages = page_numbers_kept[:min(20, len(page_numbers_kept))] if page_numbers_kept else list(range(1, min(21, len(doc_images_low) + 1)))

            pages_key = tuple(sorted(req_pages))
            page_to_reqs[pages_key].append(req)

        logger.info(f"📦 [STAGE 3] Создано {len(page_to_reqs)} групп по общим страницам")
        total_groups = len(page_to_reqs)

        for group_idx, (pages_key, reqs_group) in enumerate(page_to_reqs.items(), 1):
            if await request.is_disconnected():
                logger.warning(f"⚠️ Client disconnected at group {group_idx}/{total_groups}")
                # Возвращаем частичные результаты
                return AnalysisResponse(
                    stage=stage,
                    req_type="ТЗ",
                    requirements=analyzed_reqs,
                    summary=f"Анализ прерван: клиент отключился после обработки {len(analyzed_reqs)}/{len(requirements)} требований (группа {group_idx}/{total_groups})"
                )

            # Динамический прогресс: 70% + (0-25% в зависимости от группы)
            progress = 70 + int((group_idx / total_groups) * 25)
            update_analysis_status(
                3, 
                f"Анализ требований ({group_idx}/{total_groups} групп)", 
                progress
            )

            logger.info(f"📦 [STAGE 3] [{group_idx}/{total_groups}] Analyzing {len(reqs_group)} requirements on {len(pages_key)} pages")

            # Разбиваем на пакеты по N требований если группа большая
            for batch_start in range(0, len(reqs_group), STAGE3_BATCH_SIZE):
                batch = reqs_group[batch_start:batch_start + STAGE3_BATCH_SIZE]

                batch_results = await analyze_batch_with_high_detail(
                    system_prompt=system_prompt,
                    doc_content=doc_content,
                    page_numbers=list(pages_key),
                    requirements_batch=batch,
                    request=request,
                    pages_metadata=pages_metadata
                )

                if not batch_results:
                    # Клиент отключился во время batch анализа
                    return AnalysisResponse(
                        stage=stage,
                        req_type="ТЗ",
                        requirements=analyzed_reqs,
                        summary=f"Анализ прерван: клиент отключился во время batch анализа. Обработано {len(analyzed_reqs)}/{len(requirements)} требований"
                    )

                analyzed_reqs.extend(batch_results)

        # Сортируем по исходному порядку из ТЗ
        analyzed_reqs.sort(key=lambda r: r.number)

        # ============================================================
        # ЭТАП 7: Генерация сводки
        # ============================================================

        logger.info("📝 [STEP 3/3] Generating summary...")
        update_analysis_status(3, "Генерация отчета", 95)

        if await request.is_disconnected():
            logger.warning("⚠️ Client disconnected before summary")
            # Возвращаем результаты без summary
            return AnalysisResponse(
                stage=stage,
                req_type="ТЗ",
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
        # ЭТАП 8 (опционально): Поиск противоречий
        # ============================================================

        if STAGE4_ENABLED:
            logger.info("🔍 STAGE 4: Поиск противоречий в документации...")
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

        # Возвращаем результат с mapping листов
        parsed_result = AnalysisResponse(
            stage=stage,
            req_type="ТЗ",
            requirements=analyzed_reqs,
            summary=summary,
            sheet_to_pdf_mapping=sheet_to_pdf_mapping  # Новое поле для навигации
        )

        update_analysis_status(3, "Анализ завершен", 100)
        logger.info(f"✅ [STEP 2] Анализ завершен успешно. Проанализировано {len(analyzed_reqs)} требований.")
        return parsed_result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [STEP 2] Ошибка при анализе: {e}", exc_info=True)
        reset_analysis_status()  # Сбрасываем статус при ошибке
        raise HTTPException(status_code=500, detail=f"Ошибка анализа: {str(e)}")


# ============================
# ЗАПУСК СЕРВЕРА
# ============================

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
