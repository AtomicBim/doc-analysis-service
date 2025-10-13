"""
Трекер прогресса анализа с предсказанием времени.
Основан на реальных метриках производительности.
"""

import time
from typing import Dict, Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class StageMetrics:
    """Метрики производительности для одной стадии"""
    name: str
    time_per_page: float  # Среднее время на страницу (секунды)
    time_per_requirement: float  # Среднее время на требование (секунды)
    base_overhead: float  # Базовое время запуска стадии (секунды)


# Реальные метрики, основанные на тестах с gpt-4o-mini
STAGE_METRICS = {
    "stage1": StageMetrics(
        name="Извлечение метаданных",
        time_per_page=1.2,  # ~1.2 сек на страницу (crops + API)
        time_per_requirement=0,
        base_overhead=3.0
    ),
    "stage2": StageMetrics(
        name="Оценка релевантности",
        time_per_page=2.5,  # ~2.5 сек на страницу (Vision API high-res)
        time_per_requirement=0.5,  # +0.5 сек на каждое требование
        base_overhead=5.0
    ),
    "stage3": StageMetrics(
        name="Детальный анализ",
        time_per_page=3.0,  # ~3 сек на страницу (Vision API high-res)
        time_per_requirement=5.0,  # ~5 сек на каждое требование (анализ + генерация ответа)
        base_overhead=10.0
    ),
    "stage4": StageMetrics(
        name="Поиск противоречий",
        time_per_page=2.0,
        time_per_requirement=0,
        base_overhead=8.0
    ),
}


class ProgressTracker:
    """
    Отслеживает прогресс анализа и предсказывает оставшееся время.
    """

    def __init__(self, total_pages: int, total_requirements: int):
        self.total_pages = total_pages
        self.total_requirements = total_requirements

        # Состояние
        self.current_stage: Optional[str] = None
        self.stage_start_time: float = 0
        self.analysis_start_time: float = time.time()

        # Прогресс по стадиям
        self.stage_progress: Dict[str, Dict] = {}

        # История для динамической корректировки
        self.actual_times: Dict[str, float] = {}

        logger.info(f"🚀 ProgressTracker инициализирован: {total_pages} страниц, {total_requirements} требований")

    def start_stage(self, stage_name: str, items_count: int = 0) -> None:
        """Начать новую стадию"""
        self.current_stage = stage_name
        self.stage_start_time = time.time()

        self.stage_progress[stage_name] = {
            "items_processed": 0,
            "items_total": items_count or self._estimate_items_for_stage(stage_name),
            "start_time": self.stage_start_time,
        }

        logger.info(f"📊 Начата стадия: {stage_name}, обработка {self.stage_progress[stage_name]['items_total']} элементов")

    def update_stage_progress(self, items_processed: int) -> Dict:
        """
        Обновить прогресс текущей стадии.
        Возвращает: {"progress": 0-100, "eta_seconds": int, "current_item": str}
        """
        if not self.current_stage:
            return {"progress": 0, "eta_seconds": 0, "current_item": "Инициализация"}

        stage_info = self.stage_progress[self.current_stage]
        stage_info["items_processed"] = items_processed

        # Рассчитываем прогресс стадии
        stage_progress = min(100, (items_processed / stage_info["items_total"]) * 100) if stage_info["items_total"] > 0 else 0

        # Рассчитываем ETA для текущей стадии
        elapsed = time.time() - stage_info["start_time"]
        if items_processed > 0:
            time_per_item = elapsed / items_processed
            remaining_items = stage_info["items_total"] - items_processed
            stage_eta = time_per_item * remaining_items
        else:
            stage_eta = self._estimate_stage_time(self.current_stage)

        # Рассчитываем общий прогресс и ETA
        overall_progress, overall_eta = self._calculate_overall_progress()

        current_item_description = self._format_current_item(items_processed, stage_info["items_total"])

        logger.debug(f"📈 Прогресс {self.current_stage}: {stage_progress:.1f}% (элемент {items_processed}/{stage_info['items_total']}), ETA: {stage_eta:.0f}s")

        return {
            "progress": overall_progress,
            "stage_progress": stage_progress,
            "eta_seconds": int(overall_eta),
            "stage_eta_seconds": int(stage_eta),
            "current_item": current_item_description,
            "stage_name": STAGE_METRICS.get(self.current_stage, StageMetrics("", 0, 0, 0)).name,
        }

    def complete_stage(self) -> None:
        """Завершить текущую стадию и сохранить реальное время"""
        if not self.current_stage:
            return

        stage_info = self.stage_progress[self.current_stage]
        actual_time = time.time() - stage_info["start_time"]
        self.actual_times[self.current_stage] = actual_time

        logger.info(f"✅ Завершена стадия: {self.current_stage}, время: {actual_time:.1f}s")

        self.current_stage = None
        self.stage_start_time = 0

    def _estimate_items_for_stage(self, stage_name: str) -> int:
        """Оценить количество элементов для обработки на стадии"""
        if stage_name == "stage1":
            return min(self.total_pages, 150)  # STAGE1_MAX_PAGES
        elif stage_name == "stage2":
            return min(self.total_pages, 100)  # STAGE2_MAX_PAGES
        elif stage_name == "stage3":
            # В Stage 3 обрабатываем батчи требований
            return self.total_requirements
        elif stage_name == "stage4":
            return min(self.total_pages, 50)  # Примерная выборка
        return 10

    def _estimate_stage_time(self, stage_name: str) -> float:
        """Оценить время выполнения стадии на основе метрик"""
        metrics = STAGE_METRICS.get(stage_name)
        if not metrics:
            return 60.0  # Fallback

        items_count = self._estimate_items_for_stage(stage_name)

        estimated_time = metrics.base_overhead

        if stage_name in ["stage1", "stage2", "stage4"]:
            estimated_time += items_count * metrics.time_per_page
        elif stage_name == "stage3":
            # Stage 3: время зависит и от страниц и от требований
            avg_pages_per_req = 5  # В среднем 5 релевантных страниц на требование
            estimated_time += self.total_requirements * metrics.time_per_requirement
            estimated_time += self.total_requirements * avg_pages_per_req * (metrics.time_per_page / 10)  # Страницы обрабатываются батчами

        return estimated_time

    def _calculate_overall_progress(self) -> tuple[float, float]:
        """
        Рассчитать общий прогресс и ETA для всего анализа.
        Returns: (progress_percent, eta_seconds)
        """
        # Веса стадий (на основе типичного времени выполнения)
        stage_weights = {
            "stage1": 0.15,  # 15% - быстрая стадия
            "stage2": 0.25,  # 25% - средняя стадия
            "stage3": 0.55,  # 55% - самая долгая стадия
            "stage4": 0.05,  # 5% - опциональная, быстрая
        }

        total_progress = 0.0
        total_eta = 0.0

        for stage_name, weight in stage_weights.items():
            if stage_name in self.actual_times:
                # Стадия завершена
                total_progress += weight * 100
            elif stage_name == self.current_stage:
                # Текущая стадия
                stage_info = self.stage_progress.get(stage_name, {})
                items_processed = stage_info.get("items_processed", 0)
                items_total = stage_info.get("items_total", 1)
                stage_progress_pct = (items_processed / items_total) * 100 if items_total > 0 else 0

                total_progress += weight * stage_progress_pct

                # ETA текущей стадии
                elapsed = time.time() - stage_info.get("start_time", time.time())
                if items_processed > 0:
                    time_per_item = elapsed / items_processed
                    remaining_items = items_total - items_processed
                    total_eta += time_per_item * remaining_items
                else:
                    total_eta += self._estimate_stage_time(stage_name)

            elif stage_name not in self.actual_times:
                # Стадия еще не начата
                total_eta += self._estimate_stage_time(stage_name)

        return min(total_progress, 99.0), max(total_eta, 0)  # Не показываем 100% до полного завершения

    def _format_current_item(self, processed: int, total: int) -> str:
        """Форматировать описание текущего элемента"""
        if not self.current_stage:
            return "Инициализация"

        stage_name = STAGE_METRICS.get(self.current_stage, StageMetrics("Обработка", 0, 0, 0)).name

        if self.current_stage == "stage1":
            return f"{stage_name}: страница {processed}/{total}"
        elif self.current_stage == "stage2":
            return f"{stage_name}: страница {processed}/{total}"
        elif self.current_stage == "stage3":
            return f"{stage_name}: требование {processed}/{total}"
        elif self.current_stage == "stage4":
            return f"{stage_name}: страница {processed}/{total}"

        return f"{stage_name}: элемент {processed}/{total}"

    def get_summary(self) -> Dict:
        """Получить итоговую сводку по производительности"""
        total_time = time.time() - self.analysis_start_time

        summary = {
            "total_time_seconds": total_time,
            "total_pages": self.total_pages,
            "total_requirements": self.total_requirements,
            "stages": {},
        }

        for stage_name, actual_time in self.actual_times.items():
            estimated_time = self._estimate_stage_time(stage_name)
            summary["stages"][stage_name] = {
                "name": STAGE_METRICS.get(stage_name, StageMetrics("", 0, 0, 0)).name,
                "actual_time": actual_time,
                "estimated_time": estimated_time,
                "difference": actual_time - estimated_time,
            }

        logger.info(f"📊 Итоговая сводка анализа: {total_time:.1f}s для {self.total_pages} страниц и {self.total_requirements} требований")

        return summary
