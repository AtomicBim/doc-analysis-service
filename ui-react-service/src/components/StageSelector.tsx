/**
 * Компонент для выбора стадии проекта
 * Выделен из Header для лучшей связности
 */

import React from 'react';

interface StageSelectorProps {
  value: string;
  onChange: (stage: string) => void;
  disabled?: boolean;
}

const StageSelector: React.FC<StageSelectorProps> = ({
  value,
  onChange,
  disabled = false
}) => {
  const stages = [
    { value: 'ГК', label: 'Градостроительная концепция' },
    { value: 'ФЭ', label: 'Форэскизный проект' },
    { value: 'ЭП', label: 'Эскизный проект' }
  ];

  return (
    <div className="control-group">
      <label className="control-label">Стадия проекта</label>
      <select
        className="control-input select-input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      >
        {stages.map(stage => (
          <option key={stage.value} value={stage.value}>
            {stage.label}
          </option>
        ))}
      </select>
    </div>
  );
};

export default StageSelector;
