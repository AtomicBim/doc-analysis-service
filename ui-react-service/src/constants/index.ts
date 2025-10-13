/**
 * Константы приложения
 */

// API
export const API_URL = '/api';

// Таймауты (в миллисекундах)
export const TIMEOUTS = {
  REQUIREMENTS_EXTRACTION: 900000,  // 15 минут
  PROJECT_ANALYSIS: 2400000,        // 40 минут
  STATUS_POLLING: 2000,             // 2 секунды
  NOTIFICATION_SHORT: 3000,         // 3 секунды
  NOTIFICATION_LONG: 5000,          // 5 секунд
} as const;

// LocalStorage
export const STORAGE_KEYS = {
  APP_DATA: 'doc-analysis-app-data',
} as const;

// Сообщения
export const MESSAGES = {
  ERROR: {
    REQUIREMENTS_EXTRACTION: 'Произошла ошибка при извлечении требований.',
    PROJECT_ANALYSIS: 'Произошла ошибка при анализе.',
    TZ_FILE_REQUIRED: 'Необходимо загрузить ТЗ.',
    DOC_FILE_REQUIRED: 'Необходимо загрузить проектную документацию и подтвердить требования.',
    STORAGE_CLEANUP: '⚠️ Ошибка при очистке данных',
  },
  SUCCESS: {
    STORAGE_CLEANUP: '✅ Все данные успешно очищены. Можно начать заново.',
  },
  CONFIRM: {
    RESET: '🗑️ Очистить все данные?\n\n' +
           'Это действие удалит:\n' +
           '• Извлеченные требования\n' +
           '• Результаты анализа\n' +
           '• Загруженные файлы\n' +
           '• Все сохраненные данные из памяти браузера\n\n' +
           'Продолжить?',
  },
} as const;

// Иконки для этапов анализа
export const STAGE_ICONS = {
  1: '📋',
  2: '🔍',
  3: '📊',
} as const;

