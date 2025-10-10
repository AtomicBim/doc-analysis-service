
import React from 'react';
import { Requirement } from '../types';
import './RequirementList.css';

interface RequirementListProps {
  requirements: Requirement[];
  onSelect: (page: number) => void;
}

const RequirementList: React.FC<RequirementListProps> = ({ requirements, onSelect }) => {
  const extractPageNumber = (reference: string): number | null => {
    const match = reference.match(/страница (\d+)/i);
    if (match && match[1]) {
      return parseInt(match[1], 10);
    }
    const match2 = reference.match(/(\d+)/);
    if (match2 && match2[1]) {
        return parseInt(match2[1], 10);
      }
    return null;
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
            const page = extractPageNumber(req.reference);
            const statusClass = getStatusColor(req.status);
            const statusIcon = getStatusIcon(req.status);
            
            return (
              <div
                key={req.number}
                className={`requirement-card ${page ? 'clickable' : ''}`}
                onClick={() => page && onSelect(page)}
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
                    
                    <div className="detail-item">
                      <span className="detail-label">Ссылка:</span>
                      <span className="detail-value reference">{req.reference}</span>
                    </div>
                    
                    {req.discrepancies && req.discrepancies !== '-' && (
                      <div className="detail-item discrepancy">
                        <span className="detail-label">Несоответствия:</span>
                        <span className="detail-value">{req.discrepancies}</span>
                      </div>
                    )}
                    
                    {req.recommendations && req.recommendations !== '-' && (
                      <div className="detail-item recommendation">
                        <span className="detail-label">Рекомендации:</span>
                        <span className="detail-value">{req.recommendations}</span>
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
