
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { usePdfSearch } from '../hooks/usePdfSearch';
import './PdfViewer.css';

// Worker for react-pdf - используем CDN версию, совместимую с react-pdf 10.2.0
pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

interface PdfViewerProps {
  file: File | null;
  page: number | null;
  highlightText?: string;
}

const PdfViewer: React.FC<PdfViewerProps> = ({ file, page, highlightText = '' }) => {
  const [numPages, setNumPages] = useState<number | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [scale, setScale] = useState<number>(1.0);
  const viewerRef = useRef<HTMLDivElement>(null);

  // Используем custom hook для управления поиском
  const { searchText, setSearchText, clearSearch } = usePdfSearch({ highlightText, page });

  function onDocumentLoadSuccess({ numPages }: { numPages: number }) {
    setNumPages(numPages);
    setCurrentPage(1);
  }

  // Надежная прокрутка к странице с повторными попытками (рендер может задерживаться)
  useEffect(() => {
    if (!page || !viewerRef.current) return;
    let attempts = 0;
    const maxAttempts = 10;
    const tryScroll = () => {
      if (!viewerRef.current) return;
      const pageElement = viewerRef.current.querySelector(`[data-page-number="${page}"]`);
      if (pageElement) {
        (pageElement as HTMLElement).scrollIntoView({ behavior: 'smooth', block: 'start' });
        setCurrentPage(page);
      } else if (attempts < maxAttempts) {
        attempts += 1;
        setTimeout(tryScroll, 200);
      }
    };
    // Небольшая задержка, чтобы дождаться рендера
    const t = setTimeout(tryScroll, 50);
    return () => clearTimeout(t);
  }, [page, numPages, scale, file]);

  // Оптимизированная подсветка текста на странице
  const highlightTextOnPage = useCallback(() => {
    if (!viewerRef.current || !searchText || !page) return;

    // Очищаем предыдущие подсветки
    const allTextLayers = viewerRef.current.querySelectorAll('.textLayer');
    allTextLayers.forEach(textLayer => {
      textLayer.querySelectorAll('.highlighted-text').forEach(el => {
        el.classList.remove('highlighted-text');
      });
    });

    // Даем время на отрисовку текстового слоя
    const timer = setTimeout(() => {
      const pageWrapper = viewerRef.current?.querySelector(`[data-page-number="${page}"]`);
      if (!pageWrapper) return;

      const textLayer = pageWrapper.querySelector('.textLayer');
      if (!textLayer) {
        console.log('Текстовый слой не найден на странице', page, '. PDF может содержать только изображения.');
        return;
      }

      // Ищем текст для подсветки (нечувствительно к регистру)
      const searchLower = searchText.toLowerCase();
      const textElements = textLayer.querySelectorAll('span[role="presentation"]');

      let foundAny = false;
      textElements.forEach(span => {
        const text = span.textContent?.toLowerCase() || '';

        // Проверяем, содержит ли элемент искомый текст
        if (text.includes(searchLower)) {
          span.classList.add('highlighted-text');
          foundAny = true;
        }
      });

      if (foundAny) {
        // Прокручиваем к первому найденному элементу
        const firstHighlight = textLayer.querySelector('.highlighted-text');
        if (firstHighlight) {
          firstHighlight.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        console.log('✅ Текст найден и подсвечен на странице', page, ':', searchText);
      } else {
        console.warn('❌ Текст не найден на странице', page, ':', searchText);
      }
    }, 500); // Даем время на рендеринг текстового слоя

    return () => clearTimeout(timer);
  }, [searchText, page]);

  // Запускаем подсветку при изменении searchText или page
  useEffect(() => {
    const cleanup = highlightTextOnPage();
    return cleanup;
  }, [highlightTextOnPage]);

  const handleZoomIn = () => {
    setScale(prev => Math.min(prev + 0.2, 3.0));
  };

  const handleZoomOut = () => {
    setScale(prev => Math.max(prev - 0.2, 0.5));
  };

  const handleResetZoom = () => {
    setScale(1.0);
  };

  if (!file) {
    return (
      <div className="pdf-viewer-empty">
        <div className="empty-icon">📄</div>
        <p className="empty-text">Документ PDF будет отображен здесь</p>
        <p className="empty-hint">Выполните анализ для просмотра документации</p>
      </div>
    );
  }

  return (
    <div className="pdf-viewer-container">
      <div className="pdf-viewer-toolbar">
        <div className="toolbar-info">
          <span className="page-info">
            Страница {currentPage} из {numPages || '?'}
          </span>
          {searchText && (
            <span className="search-indicator" title={`Поиск: ${searchText}`}>
              🔍 "{searchText.substring(0, 30)}..."
            </span>
          )}
        </div>
        <div className="toolbar-controls">
          <button className="toolbar-button" onClick={handleZoomOut} title="Уменьшить">
            🔍−
          </button>
          <span className="zoom-level">{Math.round(scale * 100)}%</span>
          <button className="toolbar-button" onClick={handleZoomIn} title="Увеличить">
            🔍+
          </button>
          <button className="toolbar-button" onClick={handleResetZoom} title="Сбросить масштаб">
            ↺
          </button>
          {searchText && (
            <button
              className="toolbar-button clear-search"
              onClick={clearSearch}
              title="Очистить поиск"
            >
              ✕
            </button>
          )}
        </div>
      </div>
      <div ref={viewerRef} className="pdf-viewer-content">
        <Document 
          file={file} 
          onLoadSuccess={onDocumentLoadSuccess}
          loading={
            <div className="pdf-loading">
              <div className="spinner-large"></div>
              <p>Загрузка документа...</p>
            </div>
          }
          error={
            <div className="pdf-error">
              <span className="error-icon">⚠️</span>
              <p>Ошибка загрузки PDF</p>
            </div>
          }
        >
          {Array.from(new Array(numPages), (el, index) => (
            <div key={`page_${index + 1}`} className="pdf-page-wrapper">
              <Page 
                pageNumber={index + 1} 
                scale={scale}
                renderTextLayer={true}
                renderAnnotationLayer={true}
              />
              {/* Подсветка добавлена через CSS стили text-layer */}
            </div>
          ))}
        </Document>
      </div>
    </div>
  );
};

export default PdfViewer;
