/**
 * Custom hook для работы с localStorage
 */

import { useState, useEffect } from 'react';

interface UseLocalStorageOptions<T> {
  key: string;
  initialValue: T;
  onRestore?: (data: T) => void;
  onError?: (error: unknown) => void;
}

export function useLocalStorage<T>({
  key,
  initialValue,
  onRestore,
  onError,
}: UseLocalStorageOptions<T>) {
  const [storedValue, setStoredValue] = useState<T>(initialValue);

  // Восстановление из localStorage при монтировании
  useEffect(() => {
    try {
      const item = localStorage.getItem(key);
      if (item) {
        const parsed = JSON.parse(item) as T;
        setStoredValue(parsed);
        onRestore?.(parsed);
      }
    } catch (error) {
      console.warn(`⚠️ Ошибка восстановления данных из localStorage (${key}):`, error);
      onError?.(error);
      // Очищаем поврежденные данные
      localStorage.removeItem(key);
    }
  }, [key]); // Только при монтировании

  // Сохранение в localStorage при изменении
  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(storedValue));
      console.log(`💾 Данные сохранены в localStorage (${key})`);
    } catch (error) {
      console.warn(`⚠️ Ошибка сохранения данных в localStorage (${key}):`, error);
      onError?.(error);
    }
  }, [key, storedValue]);

  // Функция для очистки
  const clearStorage = () => {
    try {
      localStorage.removeItem(key);
      console.log(`🗑️ Данные удалены из localStorage (${key})`);
      setStoredValue(initialValue);
    } catch (error) {
      console.warn(`⚠️ Ошибка очистки localStorage (${key}):`, error);
      throw error;
    }
  };

  return {
    storedValue,
    setStoredValue,
    clearStorage,
  };
}

