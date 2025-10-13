/**
 * Утилиты для форматирования ошибок API
 */

import axios from 'axios';

export function formatApiError(error: unknown, defaultMessage: string): string {
  if (axios.isAxiosError(error) && error.response) {
    return `Ошибка API: ${error.response.status} - ${error.response.data.detail || error.message}`;
  }
  
  if (error instanceof Error && error.message) {
    return error.message;
  }
  
  return defaultMessage;
}

