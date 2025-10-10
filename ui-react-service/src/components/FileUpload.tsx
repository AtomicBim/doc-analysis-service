/**
 * Компонент для загрузки файлов
 * Выделен из Header для лучшей связности
 */

import React from 'react';

interface FileUploadProps {
  label: string;
  accept: string;
  fileName?: string;
  onChange: (file: File | null) => void;
  disabled?: boolean;
}

const FileUpload: React.FC<FileUploadProps> = ({
  label,
  accept,
  fileName,
  onChange,
  disabled = false
}) => {
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      onChange(e.target.files[0]);
    }
  };

  return (
    <div className="control-group">
      <label className="control-label">
        {label}
        {fileName && <span className="file-name">✓ {fileName}</span>}
      </label>
      <div className="file-input-wrapper">
        <input
          type="file"
          id={`file-${label.replace(/\s+/g, '-').toLowerCase()}`}
          className="file-input"
          accept={accept}
          onChange={handleFileChange}
          disabled={disabled}
        />
        <label
          htmlFor={`file-${label.replace(/\s+/g, '-').toLowerCase()}`}
          className="file-input-label"
        >
          {fileName ? 'Изменить файл' : 'Выбрать файл'}
        </label>
      </div>
    </div>
  );
};

export default FileUpload;
