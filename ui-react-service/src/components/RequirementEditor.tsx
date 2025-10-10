import React, { useState } from 'react';
import './RequirementEditor.css';

export interface EditableRequirement {
  number: number;
  text: string;
  section?: string;
  selected: boolean;
}

interface RequirementEditorProps {
  requirements: EditableRequirement[];
  onConfirm: (requirements: EditableRequirement[]) => void;
  onCancel: () => void;
}

const RequirementEditor: React.FC<RequirementEditorProps> = ({
  requirements,
  onConfirm,
  onCancel
}) => {
  const [editedRequirements, setEditedRequirements] = useState<EditableRequirement[]>(
    requirements.map(req => ({ ...req }))
  );
  const [editingId, setEditingId] = useState<number | null>(null);
  const [selectAll, setSelectAll] = useState(true);

  const handleToggle = (number: number) => {
    setEditedRequirements(prev =>
      prev.map(req =>
        req.number === number ? { ...req, selected: !req.selected } : req
      )
    );
  };

  const handleTextChange = (number: number, newText: string) => {
    setEditedRequirements(prev =>
      prev.map(req =>
        req.number === number ? { ...req, text: newText } : req
      )
    );
  };

  const handleSelectAll = (selected: boolean) => {
    setSelectAll(selected);
    setEditedRequirements(prev =>
      prev.map(req => ({ ...req, selected }))
    );
  };

  const selectedCount = editedRequirements.filter(req => req.selected).length;
  const totalCount = editedRequirements.length;

  return (
    <div className="requirement-editor-overlay">
      <div className="requirement-editor-container">
        <div className="editor-header">
          <h2>📋 Проверьте извлеченные требования</h2>
          <p className="editor-subtitle">
            Выберите требования для анализа и при необходимости отредактируйте их
          </p>
        </div>

        <div className="editor-controls">
          <div className="select-all-control">
            <label className="checkbox-label">
              <input
                type="checkbox"
                className="checkbox-input"
                checked={selectAll}
                onChange={(e) => handleSelectAll(e.target.checked)}
              />
              <span>Выбрать все ({selectedCount}/{totalCount})</span>
            </label>
          </div>

          <div className="stats">
            <span className="stat-badge">
              Всего требований: {totalCount}
            </span>
            <span className="stat-badge stat-selected">
              ✓ Выбрано: {selectedCount}
            </span>
          </div>
        </div>

        <div className="requirements-editor-list">
          {editedRequirements.map((req) => (
            <div
              key={req.number}
              className={`requirement-editor-card ${!req.selected ? 'disabled' : ''}`}
            >
              <div className="requirement-editor-header">
                <label className="requirement-checkbox">
                  <input
                    type="checkbox"
                    checked={req.selected}
                    onChange={() => handleToggle(req.number)}
                  />
                  <span className="requirement-number">#{req.number}</span>
                </label>
                {req.section && (
                  <span className="requirement-section">{req.section}</span>
                )}
              </div>

              <div className="requirement-editor-content">
                {editingId === req.number ? (
                  <div className="requirement-edit-mode">
                    <textarea
                      className="requirement-textarea"
                      value={req.text}
                      onChange={(e) => handleTextChange(req.number, e.target.value)}
                      rows={4}
                      autoFocus
                    />
                    <div className="edit-actions">
                      <button
                        className="btn-save"
                        onClick={() => setEditingId(null)}
                      >
                        ✓ Сохранить
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="requirement-view-mode">
                    <p className="requirement-text">{req.text}</p>
                    <button
                      className="btn-edit"
                      onClick={() => setEditingId(req.number)}
                    >
                      ✎ Редактировать
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="editor-footer">
          <button className="btn-cancel" onClick={onCancel}>
            Отмена
          </button>
          <button
            className="btn-confirm"
            onClick={() => onConfirm(editedRequirements)}
            disabled={selectedCount === 0}
          >
            ✓ Подтвердить и продолжить ({selectedCount} требований)
          </button>
        </div>
      </div>
    </div>
  );
};

export default RequirementEditor;

