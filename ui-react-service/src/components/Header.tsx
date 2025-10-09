
import React, { useState } from 'react';
import axios from 'axios';
import { Requirement } from '../types';

interface HeaderProps {
  onAnalysisComplete: (
    requirements: Requirement[],
    summary: string,
    pdfFile: File
  ) => void;
}

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8002';

const Header: React.FC<HeaderProps> = ({ onAnalysisComplete }) => {
  const [stage, setStage] = useState('ФЭ');
  const [checkTu, setCheckTu] = useState(false);
  const [tzFile, setTzFile] = useState<File | null>(null);
  const [docFile, setDocFile] = useState<File | null>(null);
  const [tuFile, setTuFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAnalyze = async () => {
    if (!tzFile || !docFile) {
      setError('Необходимо загрузить ТЗ и файл документации.');
      return;
    }

    setLoading(true);
    setError(null);

    const formData = new FormData();
    formData.append('stage', stage);
    formData.append('check_tu', String(checkTu));
    formData.append('tz_document', tzFile);
    formData.append('doc_document', docFile);
    if (checkTu && tuFile) {
      formData.append('tu_document', tuFile);
    }

    try {
      const response = await axios.post(`${API_URL}/analyze`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        timeout: 2400000, // 40 minutes
      });

      const { requirements, summary } = response.data;
      onAnalysisComplete(requirements, summary, docFile);
    } catch (err: any) {
      let errorMessage = 'Произошла ошибка при анализе.';
      if (axios.isAxiosError(err) && err.response) {
        errorMessage = `Ошибка API: ${err.response.status} - ${err.response.data.detail || err.message}`;
      } else if (err.message) {
        errorMessage = err.message;
      }
      setError(errorMessage);
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <header className="App-header">
      <h2>Анализ проектной документации</h2>
      <div className="controls">
        <div>
          <label>Стадия: </label>
          <select value={stage} onChange={(e) => setStage(e.target.value)}>
            <option value="ГК">Градостроительная концепция</option>
            <option value="ФЭ">Форэскизный проект</option>
            <option value="ЭП">Эскизный проект</option>
          </select>
        </div>
        <div>
          <label>
            <input
              type="checkbox"
              checked={checkTu}
              onChange={(e) => setCheckTu(e.target.checked)}
            />
            Добавить проверку ТУ
          </label>
        </div>
        <div>
          <label>ТЗ: </label>
          <input type="file" onChange={(e) => setTzFile(e.target.files ? e.target.files[0] : null)} />
        </div>
        <div>
          <label>Документация: </label>
          <input type="file" onChange={(e) => setDocFile(e.target.files ? e.target.files[0] : null)} />
        </div>
        {checkTu && (
          <div>
            <label>ТУ: </label>
            <input type="file" onChange={(e) => setTuFile(e.target.files ? e.target.files[0] : null)} />
          </div>
        )}
        <button onClick={handleAnalyze} disabled={loading}>
          {loading ? 'Анализ...' : 'Выполнить анализ'}
        </button>
      </div>
      {error && <div style={{ color: 'red' }}>{error}</div>}
    </header>
  );
};

export default Header;
