
import React from 'react';
import { Requirement } from '../types';
import './RequirementList.css';

interface RequirementListProps {
  requirements: Requirement[];
  onSelect: (page: number, highlightText?: string) => void;
}

interface PageReference {
  page: number;
  description: string;
}

const RequirementList: React.FC<RequirementListProps> = ({ requirements, onSelect }) => {
  // Извлекаем упоминания листов с обоснованиями из решения
  const extractPageReferences = (solution: string): PageReference[] => {
    const references: PageReference[] = [];
    
    // Regex для поиска упоминаний листов: "на листе 5", "лист 17", "странице 10" и т.д.
    const pageRegex = /(?:на\s+)?(?:лист[е]?|страниц[ае])\s+(\d+)\s*[-–—]?\s*([^.;]*(?:[.;][^;.]*?(?=(?:лист[е]?|страниц[ае]|\d+\s*[-–—]|$)))?)/gi;
    
    let match;
    while ((match = pageRegex.exec(solution)) !== null) {
      const pageNum = parseInt(match[1], 10);
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
      
      if (pageNum && pageNum < 1000) {
        references.push({ page: pageNum, description });
      }
    }
    
    // Если не нашли ничего с помощью regex, пробуем альтернативный подход
    if (references.length === 0) {
      // Разбиваем текст на предложения
      const sentences = solution.split(/[.;]+/).filter(s => s.trim());
      
      sentences.forEach(sentence => {
        const simplePageRegex = /(?:лист[е]?|страниц[ае])\s+(\d+)/i;
        const match = sentence.match(simplePageRegex);
        
        if (match) {
          const pageNum = parseInt(match[1], 10);
          let description = sentence.trim();
          
          // Убираем начало предложения до упоминания листа
          const pageIndex = description.search(simplePageRegex);
          if (pageIndex > 0) {
            description = description.substring(pageIndex + match[0].length).trim();
          }
          
          if (description.length > 150) {
            description = description.substring(0, 147) + '...';
          }
          
          if (pageNum && pageNum < 1000) {
            references.push({ page: pageNum, description: description || sentence.trim() });
          }
        }
      });
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
            const pageReferences = extractPageReferences(req.solution_description);
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
                            <div key={idx} className="reference-item">
                              <div className="reference-info">
                                <span className="reference-page">Лист {ref.page}</span>
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
                                title={`Перейти к листу ${ref.page} и найти: ${ref.description}`}
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
