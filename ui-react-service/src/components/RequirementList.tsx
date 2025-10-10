
import React from 'react';
import { Requirement } from '../types';
import './RequirementList.css';

interface RequirementListProps {
  requirements: Requirement[];
  onSelect: (page: number, highlightText?: string) => void;
  sheetToPdfMapping?: Record<string, number>;  // Mapping: sheet_number → pdf_page_number
}

interface PageReference {
  page: number;  // PDF page number (порядковый номер для навигации)
  sheetNumber: string;  // Sheet number (реальный номер листа для отображения)
  description: string;
}

const RequirementList: React.FC<RequirementListProps> = ({ requirements, onSelect, sheetToPdfMapping = {} }) => {
  console.log('🗺️ RequirementList получил mapping:', sheetToPdfMapping);
  
  // Извлекаем упоминания листов из решения и из поля reference
  const extractPageReferences = (solution: string, referenceField?: string): PageReference[] => {
    const references: PageReference[] = [];
    
    // СНАЧАЛА парсим поле reference - там точные ссылки от API
    if (referenceField && referenceField.trim() && referenceField !== '-') {
      // Парсим обозначения листов: "АР-01", "5", "КР-03.1" и т.д.
      const sheetRefs = referenceField.match(/[\w\d]+(?:[-–—.]\w*)*/g) || [];
      
      sheetRefs.forEach(sheetRef => {
        let pdfPageNum: number | null = null;
        
        // Ищем в mapping
        if (sheetToPdfMapping[sheetRef]) {
          pdfPageNum = sheetToPdfMapping[sheetRef];
          console.log(`✅ [reference] ${sheetRef} → страница ${pdfPageNum}`);
        } else {
          // Fallback: если это число
          const numericPage = parseInt(sheetRef, 10);
          if (!isNaN(numericPage) && numericPage > 0 && numericPage < 500) {
            pdfPageNum = numericPage;
            console.log(`⚠️ [reference fallback] ${sheetRef} → страница ${pdfPageNum}`);
          }
        }
        
        if (pdfPageNum && !references.some(r => r.page === pdfPageNum)) {
          references.push({
            page: pdfPageNum,
            sheetNumber: sheetRef,
            description: solution.substring(0, 100).trim() + '...'  // Краткое описание из начала решения
          });
        }
      });
    }
    
    // ПОТОМ парсим текст решения для дополнительных ссылок
    // Regex для поиска упоминаний листов:
    // Захватывает: "лист 5", "Лист АР-03", "странице 26", "лист КР-05.1" и т.д.
    const pageRegex = /(?:на\s+)?(?:лист[е]?|страниц[ае])\s+([\w\d]+(?:[-–—.]\w*)*)\s*[-–—]?\s*([^.;]*(?:[.;][^;.]*?(?=(?:лист[е]?|страниц[ае]|[\w\d]+\s*[-–—]|$)))?)/gi;
    
    let match;
    while ((match = pageRegex.exec(solution)) !== null) {
      const sheetRef = match[1].trim();  // Может быть "5", "АР-03", "26" и т.д.
      let description = match[2] ? match[2].trim() : '';
      
      // Очищаем описание от лишних символов
      description = description.replace(/^[-–—:,;\s]+/, '').replace(/[;.,]+$/, '').trim();
      
      // Если описание пустое или слишком короткое, берем контекст после упоминания листа
      if (!description || description.length < 10) {
        const startIndex = match.index + match[0].length;
        const contextLength = 100;
        const endIndex = Math.min(startIndex + contextLength, solution.length);
        description = solution.substring(startIndex, endIndex).trim();
        
        // Обрезаем до конца предложения
        const sentenceEnd = description.search(/[.;]/);
        if (sentenceEnd !== -1) {
          description = description.substring(0, sentenceEnd).trim();
        }
      }
      
      // Если описание все еще слишком длинное, обрезаем
      if (description.length > 150) {
        description = description.substring(0, 147) + '...';
      }
      
      // Ищем соответствие в mapping
      let pdfPageNum: number | null = null;
      
      // Пробуем найти точное совпадение
      if (sheetToPdfMapping[sheetRef]) {
        pdfPageNum = sheetToPdfMapping[sheetRef];
        console.log(`✅ Найдено соответствие: ${sheetRef} → страница ${pdfPageNum}`);
      } else {
        // Fallback: если это число, используем как есть
        const numericPage = parseInt(sheetRef, 10);
        if (!isNaN(numericPage) && numericPage > 0 && numericPage < 500) {
          pdfPageNum = numericPage;
          console.log(`⚠️ Используем fallback для листа ${sheetRef} → страница ${pdfPageNum}`);
        } else {
          console.warn(`❌ Не найден mapping для листа: ${sheetRef}`);
        }
      }
      
      if (pdfPageNum && !references.some(r => r.page === pdfPageNum)) {
        // Улучшаем description - извлекаем ключевые слова из контекста
        let betterDescription = description;
        if (!description || description.length < 20) {
          // Ищем существительные и технические термины рядом с упоминанием листа
          const context = solution.substring(Math.max(0, match.index - 50), match.index + 150);
          const keywords = context.match(/[А-ЯЁ][а-яё]+(?:\s+[а-яё]+){0,3}/g);
          if (keywords && keywords.length > 0) {
            betterDescription = keywords.slice(0, 3).join(', ');
          }
        }
        
        references.push({ 
          page: pdfPageNum,  // PDF page number для навигации
          sheetNumber: sheetRef,  // Реальный номер листа для отображения
          description: betterDescription || solution.substring(0, 80).trim()
        });
      }
    }

    // Если ничего не найдено - попробуем простой поиск числовых ссылок
    if (references.length === 0 && referenceField && referenceField !== '-') {
      console.log('⚠️ Regex не нашел ссылок, пробуем простой поиск в reference field');
      const simpleNumbers = referenceField.match(/\b\d{1,3}\b/g);
      if (simpleNumbers) {
        simpleNumbers.forEach(numStr => {
          const pageNum = parseInt(numStr, 10);
          if (pageNum > 0 && pageNum < 500 && !references.some(r => r.page === pageNum)) {
            references.push({
              page: pageNum,
              sheetNumber: numStr,
              description: solution.substring(0, 100).trim() + '...'
            });
          }
        });
      }
    }
    
    // Удаляем дубликаты по номеру страницы
    const uniqueRefs = references.filter((ref, index, self) => 
      index === self.findIndex(r => r.page === ref.page)
    );
    
    return uniqueRefs.sort((a, b) => a.page - b.page);
  };

  const getStatusColor = (status: string): string => {
    if (status === 'Полностью исполнено') return 'status-complete';
    if (status === 'Частично исполнено') return 'status-partial';
    if (status === 'Не исполнено') return 'status-failed';
    return 'status-unclear';
  };

  const getStatusIcon = (status: string): string => {
    if (status === 'Полностью исполнено') return '✅';
    if (status === 'Частично исполнено') return '⚠️';
    if (status === 'Не исполнено') return '❌';
    return '❓';
  };

  return (
    <div className="requirement-list-container">
      <div className="requirement-list-header">
        <h2>Требования</h2>
        {requirements.length > 0 && (
          <div className="stats">
            <span className="stat-badge">Всего: {requirements.length}</span>
            <span className="stat-badge stat-complete">
              ✅ {requirements.filter(r => r.status === 'Полностью исполнено').length}
            </span>
            <span className="stat-badge stat-partial">
              ⚠️ {requirements.filter(r => r.status === 'Частично исполнено').length}
            </span>
            <span className="stat-badge stat-failed">
              ❌ {requirements.filter(r => r.status === 'Не исполнено').length}
            </span>
          </div>
        )}
      </div>
      
      {requirements.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">📋</div>
          <p className="empty-text">Результаты анализа появятся здесь</p>
          <p className="empty-hint">Загрузите файлы и нажмите "Выполнить анализ"</p>
        </div>
      ) : (
        <div className="requirements-list">
          {requirements.map((req) => {
            const pageReferences = extractPageReferences(req.solution_description, req.reference);
            const statusClass = getStatusColor(req.status);
            const statusIcon = getStatusIcon(req.status);
            
            return (
              <div
                key={req.number}
                className="requirement-card"
              >
                <div className="requirement-header">
                  <span className="requirement-number">#{req.number}</span>
                  <span className={`requirement-status ${statusClass}`}>
                    {statusIcon} {req.status}
                  </span>
                </div>
                
                <div className="requirement-content">
                  <p className="requirement-text">{req.requirement}</p>
                  
                  <div className="requirement-details">
                    <div className="detail-item">
                      <span className="detail-label">Решение:</span>
                      <span className="detail-value">{req.solution_description}</span>
                    </div>
                    
                    {/* Ссылки с обоснованиями */}
                    {pageReferences.length > 0 && (
                      <div className="detail-item references-section">
                        <span className="detail-label">Ссылки:</span>
                        <div className="reference-items">
                          {pageReferences.map((ref, idx) => (
                            <div key={idx} className="reference-item" onClick={(e) => {
                              e.stopPropagation();
                              onSelect(ref.page, ref.description);
                            }}
                            title={`Перейти к листу ${ref.sheetNumber}${ref.description ? ` и найти: ${ref.description}` : ''}`}>
                              <div className="reference-info">
                                <span className="reference-page">Лист {ref.sheetNumber}</span>
                                {ref.description && (
                                  <span className="reference-description">
                                    {ref.description}
                                  </span>
                                )}
                              </div>
                              <button
                                className="reference-button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onSelect(ref.page, ref.description);
                                }}
                              >
                                📄 Перейти
                              </button>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    
                    {req.discrepancies && req.discrepancies !== '-' && (
                      <div className="detail-item discrepancy">
                        <span className="detail-label">Несоответствия:</span>
                        <span className="detail-value">{req.discrepancies}</span>
                      </div>
                    )}
                  </div>
                  
                  <div className="requirement-footer">
                    <div className="confidence-bar">
                      <span className="confidence-label">Уверенность:</span>
                      <div className="confidence-progress">
                        <div 
                          className="confidence-fill" 
                          style={{ 
                            width: `${req.confidence}%`,
                            background: req.confidence >= 80 ? '#10b981' : req.confidence >= 60 ? '#f59e0b' : '#ef4444'
                          }}
                        ></div>
                      </div>
                      <span className="confidence-value">{req.confidence}%</span>
                    </div>
                    {req.section && (
                      <span className="section-badge">{req.section}</span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default RequirementList;
