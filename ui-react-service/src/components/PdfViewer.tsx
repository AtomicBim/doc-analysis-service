
import React, { useState, useEffect, useRef } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import './PdfViewer.css';

// Worker for react-pdf - используем локальный worker
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

interface PdfViewerProps {
  file: File | null;
  page: number | null;
}

const PdfViewer: React.FC<PdfViewerProps> = ({ file, page }) => {
  const [numPages, setNumPages] = useState<number | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [scale, setScale] = useState<number>(1.0);
  const viewerRef = useRef<HTMLDivElement>(null);

  function onDocumentLoadSuccess({ numPages }: { numPages: number }) {
    setNumPages(numPages);
    setCurrentPage(1);
  }

  useEffect(() => {
    if (page && viewerRef.current) {
      const pageElement = viewerRef.current.querySelector(`[data-page-number="${page}"]`);
      if (pageElement) {
        pageElement.scrollIntoView({ behavior: 'smooth' });
        setCurrentPage(page);
      }
    }
  }, [page]);

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
            </div>
          ))}
        </Document>
      </div>
    </div>
  );
};

export default PdfViewer;
