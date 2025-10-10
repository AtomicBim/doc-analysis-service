
import React from 'react';
import { Requirement } from '../types';
import { extractPageReferences, PageReference } from '../utils/pageReferences';
import './RequirementList.css';

interface RequirementListProps {
  requirements: Requirement[];
  onSelect: (page: number, highlightText?: string) => void;
  sheetToPdfMapping?: Record<string, number>;  // Mapping: sheet_number → pdf_page_number
}

const RequirementList: React.FC<RequirementListProps> = ({ requirements, onSelect, sheetToPdfMapping = {} }) => {
  console.log('🗺️ RequirementList получил mapping:', sheetToPdfMapping);

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
            const pageReferences = extractPageReferences(req.solution_description, req.reference, sheetToPdfMapping);
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
