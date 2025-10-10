/**
 * Custom hook для управления поиском текста в PDF
 */

import { useState, useEffect, useRef } from 'react';

interface UsePdfSearchProps {
  highlightText: string;
  page: number | null;
}

interface UsePdfSearchReturn {
  searchText: string;
  setSearchText: (text: string) => void;
  clearSearch: () => void;
}

export const usePdfSearch = ({ highlightText, page }: UsePdfSearchProps): UsePdfSearchReturn => {
  const [searchText, setSearchText] = useState<string>('');
  const lastHighlightRef = useRef<string>('');

  // Синхронизируем searchText с highlightText
  useEffect(() => {
    if (highlightText && highlightText !== lastHighlightRef.current) {
      setSearchText(highlightText);
      lastHighlightRef.current = highlightText;
    } else if (!highlightText) {
      setSearchText('');
      lastHighlightRef.current = '';
    }
  }, [highlightText, page]);

  const clearSearch = () => {
    setSearchText('');
    lastHighlightRef.current = '';
  };

  return {
    searchText,
    setSearchText,
    clearSearch
  };
};
