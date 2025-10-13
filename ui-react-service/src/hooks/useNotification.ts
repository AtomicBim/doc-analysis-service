/**
 * Custom hook для управления уведомлениями
 */

import { useState, useCallback, useRef, useEffect } from 'react';

export function useNotification() {
  const [notification, setNotification] = useState<string | null>(null);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Очистка таймера при размонтировании
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  const showNotification = useCallback((message: string, duration: number = 3000) => {
    // Очищаем предыдущий таймер
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }

    setNotification(message);

    // Автоматически скрываем уведомление
    timeoutRef.current = setTimeout(() => {
      setNotification(null);
      timeoutRef.current = null;
    }, duration);
  }, []);

  const hideNotification = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    setNotification(null);
  }, []);

  return {
    notification,
    showNotification,
    hideNotification,
  };
}

