/**
 * Компонент для отображения пустого состояния
 */

import React from 'react';

interface EmptyStateProps {
  icon: string;
  text: string;
  hint?: string;
  action?: string;
  className?: string;
}

const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  text,
  hint,
  action,
  className = 'empty-state',
}) => {
  return (
    <div className={className}>
      <div className="empty-icon">{icon}</div>
      <p className="empty-text">{text}</p>
      {hint && <p className="empty-hint">{hint}</p>}
      {action && <p className="empty-action">{action}</p>}
    </div>
  );
};

export default EmptyState;

