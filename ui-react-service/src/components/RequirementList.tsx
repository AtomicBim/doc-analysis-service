
import React from 'react';
import { Requirement } from '../types';

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

  return (
    <div>
      <h3>Требования</h3>
      {requirements.length === 0 ? (
        <p>Результаты анализа появятся здесь.</p>
      ) : (
        <ul>
          {requirements.map((req) => {
            const page = extractPageNumber(req.reference);
            return (
              <li
                key={req.number}
                onClick={() => page && onSelect(page)}
                style={{ cursor: page ? 'pointer' : 'default', marginBottom: '1rem' }}
              >
                <strong>Требование {req.number}:</strong> {req.requirement}
                <br />
                <em>Статус: {req.status} (Уверенность: {req.confidence}%)</em>
                <br />
                <span>Решение: {req.solution_description}</span>
                <br />
                <small>Ссылка: {req.reference}</small>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};

export default RequirementList;
