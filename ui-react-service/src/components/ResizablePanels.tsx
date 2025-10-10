import React, { useState, useRef, useEffect } from 'react';
import './ResizablePanels.css';

interface ResizablePanelsProps {
  header: React.ReactNode;
  leftPanel: React.ReactNode;
  rightPanel: React.ReactNode;
}

const ResizablePanels: React.FC<ResizablePanelsProps> = ({ header, leftPanel, rightPanel }) => {
  // Состояния для размеров
  const [headerHeight, setHeaderHeight] = useState(25); // % от высоты
  const [leftWidth, setLeftWidth] = useState(30); // % от ширины
  
  // Refs для отслеживания перетаскивания
  const isDraggingVertical = useRef(false);
  const isDraggingHorizontal = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Обработчик начала перетаскивания вертикального разделителя (header <-> content)
  const handleVerticalMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    isDraggingVertical.current = true;
  };

  // Обработчик начала перетаскивания горизонтального разделителя (left <-> right)
  const handleHorizontalMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    isDraggingHorizontal.current = true;
  };

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return;

      const containerRect = containerRef.current.getBoundingClientRect();

      // Перетаскивание вертикального разделителя (header <-> content)
      if (isDraggingVertical.current) {
        const newHeaderHeight = ((e.clientY - containerRect.top) / containerRect.height) * 100;
        // Ограничиваем: минимум 10%, максимум 60%
        setHeaderHeight(Math.max(10, Math.min(60, newHeaderHeight)));
      }

      // Перетаскивание горизонтального разделителя (left <-> right)
      if (isDraggingHorizontal.current) {
        const newLeftWidth = ((e.clientX - containerRect.left) / containerRect.width) * 100;
        // Ограничиваем: минимум 15%, максимум 70%
        setLeftWidth(Math.max(15, Math.min(70, newLeftWidth)));
      }
    };

    const handleMouseUp = () => {
      isDraggingVertical.current = false;
      isDraggingHorizontal.current = false;
    };

    // Добавляем глобальные слушатели
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  return (
    <div ref={containerRef} className="resizable-container">
      {/* Header */}
      <div className="resizable-header" style={{ height: `${headerHeight}%` }}>
        {header}
      </div>

      {/* Вертикальный разделитель (header <-> content) */}
      <div 
        className="vertical-resizer" 
        onMouseDown={handleVerticalMouseDown}
        title="Перетащите для изменения высоты заголовка"
      >
        <div className="resizer-handle">⋮</div>
      </div>

      {/* Основной контент */}
      <div className="resizable-content" style={{ height: `${100 - headerHeight}%` }}>
        {/* Левая панель */}
        <div className="resizable-left" style={{ width: `${leftWidth}%` }}>
          {leftPanel}
        </div>

        {/* Горизонтальный разделитель (left <-> right) */}
        <div 
          className="horizontal-resizer" 
          onMouseDown={handleHorizontalMouseDown}
          title="Перетащите для изменения ширины панелей"
        >
          <div className="resizer-handle">⋯</div>
        </div>

        {/* Правая панель */}
        <div className="resizable-right" style={{ width: `${100 - leftWidth}%` }}>
          {rightPanel}
        </div>
      </div>
    </div>
  );
};

export default ResizablePanels;

