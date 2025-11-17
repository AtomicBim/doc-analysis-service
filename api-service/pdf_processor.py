"""
Централизованный PDF процессор для анализа документации.
Убирает избыточность в обработке PDF и улучшает связность.
"""

import asyncio
import logging
from typing import List, Dict, Any, Tuple, Optional
import fitz  # pymupdf
from PIL import Image
import io
import base64

logger = logging.getLogger(__name__)


class PDFProcessor:
    """
    Централизованный процессор для работы с PDF файлами.
    Объединяет общую логику обработки изображений и страниц.
    """

    def __init__(self, doc_content: bytes, filename: str):
        self.doc_content = doc_content
        self.filename = filename
        self._doc = None

    def __enter__(self):
        """Context manager для безопасного открытия PDF"""
        self._doc = fitz.open(stream=self.doc_content, filetype="pdf")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager для безопасного закрытия PDF"""
        if self._doc:
            self._doc.close()

    @property
    def page_count(self) -> int:
        """Количество страниц в документе"""
        if not self._doc:
            raise RuntimeError("PDF не открыт. Используйте в контексте 'with'")
        return len(self._doc)

    def get_page(self, page_num: int) -> fitz.Page:
        """Получить страницу по номеру (1-based)"""
        if not self._doc:
            raise RuntimeError("PDF не открыт. Используйте в контексте 'with'")
        if page_num < 1 or page_num > self.page_count:
            raise ValueError(f"Неверный номер страницы: {page_num}")
        return self._doc[page_num - 1]

    def extract_pages_as_images(
        self,
        page_numbers: List[int],
        dpi: int = 100,
        quality: int = 70,
        detail: str = "low"
    ) -> List[str]:
        """
        Извлечь выбранные страницы как base64-encoded изображения.

        Args:
            page_numbers: Список номеров страниц (1-based)
            dpi: Качество рендеринга
            quality: JPEG качество (0-100)
            detail: Vision detail level

        Returns:
            Список base64 строк изображений
        """
        images = []
        logger.info(f"📄 [PDF] Извлечение {len(page_numbers)} страниц из {self.filename} (dpi={dpi}, quality={quality})")

        for page_num in page_numbers:
            try:
                page = self.get_page(page_num)
                pix = page.get_pixmap(dpi=dpi)

                # Конвертация в PIL Image
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                # Сохранение как JPEG
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='JPEG', quality=quality)
                base64_image = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')

                images.append(base64_image)

            except Exception as e:
                logger.error(f"❌ [PDF] Ошибка извлечения страницы {page_num}: {e}")
                continue

        logger.info(f"✅ [PDF] Извлечено {len(images)}/{len(page_numbers)} изображений")
        return images

    def extract_page_crops(
        self,
        page_num: int,
        crop_areas: List[Dict[str, float]],
        dpi: int = 100,
        quality: int = 70
    ) -> List[str]:
        """
        Извлечь области (crops) с одной страницы.

        Args:
            page_num: Номер страницы (1-based)
            crop_areas: Список областей для вырезания
            dpi: Качество рендеринга
            quality: JPEG качество

        Returns:
            Список base64 изображений областей
        """
        crops = []
        try:
            page = self.get_page(page_num)
            pix = page.get_pixmap(dpi=dpi)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            width, height = img.size

            for crop_config in crop_areas:
                # Вычисление координат вырезания
                left = int(width * crop_config['left'])
                top = int(height * crop_config['top'])
                right = int(width * crop_config['right'])
                bottom = int(height * crop_config['bottom'])

                # Вырезание области
                crop = img.crop((left, top, right, bottom))

                # Сохранение как base64
                img_byte_arr = io.BytesIO()
                crop.save(img_byte_arr, format='JPEG', quality=quality)
                base64_crop = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
                crops.append(base64_crop)

        except Exception as e:
            logger.error(f"❌ [PDF] Ошибка извлечения crops со страницы {page_num}: {e}")

        return crops

    def extract_text_pages(self, max_pages: int = 200) -> List[str]:
        """Быстро извлечь текст по страницам для префильтрации."""
        texts = []
        pages_to_process = min(self.page_count, max_pages)

        for i in range(pages_to_process):
            try:
                page = self._doc[i]
                page_text = page.get_text() or ""
                texts.append(page_text)
            except Exception as e:
                logger.error(f"❌ [PDF] Ошибка извлечения текста страницы {i+1}: {e}")
                texts.append("")

        return texts


class PDFBatchProcessor:
    """
    Пакетный процессор для оптимизации работы с несколькими страницами.
    Использует параллельную обработку для улучшения производительности.
    """

    def __init__(self, doc_content: bytes, filename: str):
        self.doc_content = doc_content
        self.filename = filename

    async def extract_pages_batch(
        self,
        page_numbers: List[int],
        dpi: int = 100,
        quality: int = 70,
        max_concurrent: int = 5
    ) -> List[str]:
        """
        Параллельное извлечение нескольких страниц.

        Args:
            page_numbers: Список номеров страниц (1-based)
            dpi: Качество рендеринга
            quality: JPEG качество
            max_concurrent: Максимальное количество одновременных задач

        Returns:
            Список base64 изображений в порядке page_numbers
        """
        async def extract_single_page(page_num: int) -> str:
            """Извлечение одной страницы"""
            with PDFProcessor(self.doc_content, self.filename) as processor:
                images = processor.extract_pages_as_images([page_num], dpi, quality)
                return images[0] if images else ""

        # Разбиваем на батчи для параллельной обработки
        results = []
        for i in range(0, len(page_numbers), max_concurrent):
            batch = page_numbers[i:i + max_concurrent]
            logger.info(f"📄 [BATCH] Обработка батча {i//max_concurrent + 1}: страницы {batch}")

            # Создаем задачи для параллельного выполнения
            tasks = [extract_single_page(page_num) for page_num in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Обрабатываем результаты
            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    logger.error(f"❌ [BATCH] Ошибка страницы {batch[j]}: {result}")
                    results.append("")  # Пустая строка для неудачных страниц
                else:
                    results.append(result)

        return results
