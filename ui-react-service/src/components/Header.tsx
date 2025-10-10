
import React, { useState } from 'react';
import axios from 'axios';
import { Requirement } from '../types';
import './Header.css';

interface HeaderProps {
  onAnalysisComplete: (
    requirements: Requirement[],
    summary: string
  ) => void;
  onDocFileChange: (file: File | null) => void;
}

const API_URL = '/api';

const Header: React.FC<HeaderProps> = ({ onAnalysisComplete, onDocFileChange }) => {
  const [stage, setStage] = useState('ФЭ');
  const [checkTu, setCheckTu] = useState(false);
  const [tzFile, setTzFile] = useState<File | null>(null);
  const [docFile, setDocFile] = useState<File | null>(null);
  const [tuFile, setTuFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analysisProgress, setAnalysisProgress] = useState(0);
  const [currentStage, setCurrentStage] = useState('');

  const handleAnalyze = async () => {
    if (!tzFile || !docFile) {
      setError('Необходимо загрузить ТЗ и файл документации.');
      return; 
    }

    setLoading(true);
    setError(null);
    setAnalysisProgress(0);
    setCurrentStage('');

  // Симуляция прогресса через этапы (с учетом бэкенд-логов): удерживаем <=95% до ответа API
  const stages = [
      { name: 'Извлечение текста из ТЗ', duration: 15000, progress: 12 },
      { name: 'Сегментация требований', duration: 10000, progress: 22 },
      { name: 'Stage 1: Извлечение метаданных', duration: 20000, progress: 38 },
      { name: 'Stage 2: Оценка релевантности', duration: 30000, progress: 55 },
      { name: 'Stage 3: Детальный анализ', duration: 240000, progress: 92 },
      { name: 'Stage 4: Поиск противоречий', duration: 30000, progress: 95 },
    ];

    let currentStageIndex = 0;
    let elapsed = 0;
    const totalStageDuration = stages.reduce((acc, s) => acc + s.duration, 0);
    const tick = 500; // обновление каждые 0.5с для плавности
    const progressInterval = setInterval(() => {
      if (currentStageIndex < stages.length) {
        const stage = stages[currentStageIndex];
        elapsed += tick;
        setCurrentStage(stage.name);
        // Плавное приближение к целевому прогрессу этапа
        setAnalysisProgress((prev) => {
          const target = stage.progress;
          const step = Math.max(0.5, (target - prev) * 0.05);
          const next = Math.min(prev + step, target);
          return Math.min(next, 95);
        });
        if (elapsed >= stage.duration) {
          currentStageIndex++;
          elapsed = 0;
        }
      }
    }, tick);

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

      clearInterval(progressInterval);
      setAnalysisProgress(100);
      setCurrentStage('Завершено');

      const { requirements, summary } = response.data;
      onAnalysisComplete(requirements, summary);
    } catch (err: any) {
      clearInterval(progressInterval);
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
      setTimeout(() => {
        setAnalysisProgress(0);
        setCurrentStage('');
      }, 2000);
    }
  };

  const handleFileChange = (setter: React.Dispatch<React.SetStateAction<File | null>>, isDocFile: boolean = false) => 
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files && e.target.files.length > 0) {
        const file = e.target.files[0];
        setter(file);
        if (isDocFile) {
          onDocFileChange(file); // Показываем PDF сразу
        }
      }
    };

  return (
    <header className="header">
      <div className="header-content">
        <div className="header-title">
          <h1>Анализ проектной документации</h1>
          <p className="header-subtitle">Автоматическая проверка соответствия требованиям ТЗ</p>
        </div>
        
        <div className="controls-grid">
          <div className="control-group">
            <label className="control-label">Стадия проекта</label>
            <select 
              className="control-input select-input" 
              value={stage} 
              onChange={(e) => setStage(e.target.value)}
            >
              <option value="ГК">Градостроительная концепция</option>
              <option value="ФЭ">Форэскизный проект</option>
              <option value="ЭП">Эскизный проект</option>
            </select>
          </div>

          <div className="control-group checkbox-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                className="checkbox-input"
                checked={checkTu}
                onChange={(e) => setCheckTu(e.target.checked)}
              />
              <span className="checkbox-text">Добавить проверку ТУ</span>
            </label>
          </div>

          <div className="control-group">
            <label className="control-label">
              Техническое задание (ТЗ)
              {tzFile && <span className="file-name">✓ {tzFile.name}</span>}
            </label>
            <div className="file-input-wrapper">
              <input 
                type="file" 
                id="tz-file"
                className="file-input" 
                accept=".pdf"
                onChange={handleFileChange(setTzFile)} 
              />
              <label htmlFor="tz-file" className="file-input-label">
                {tzFile ? 'Изменить файл' : 'Выбрать файл'}
              </label>
            </div>
          </div>

          <div className="control-group">
            <label className="control-label">
              Проектная документация
              {docFile && <span className="file-name">✓ {docFile.name}</span>}
            </label>
            <div className="file-input-wrapper">
              <input 
                type="file" 
                id="doc-file"
                className="file-input" 
                accept=".pdf"
                onChange={handleFileChange(setDocFile, true)} 
              />
              <label htmlFor="doc-file" className="file-input-label">
                {docFile ? 'Изменить файл' : 'Выбрать файл'}
              </label>
            </div>
          </div>

          {checkTu && (
            <div className="control-group">
              <label className="control-label">
                Технические условия (ТУ)
                {tuFile && <span className="file-name">✓ {tuFile.name}</span>}
              </label>
              <div className="file-input-wrapper">
                <input 
                  type="file" 
                  id="tu-file"
                  className="file-input" 
                  accept=".pdf"
                  onChange={handleFileChange(setTuFile)} 
                />
                <label htmlFor="tu-file" className="file-input-label">
                  {tuFile ? 'Изменить файл' : 'Выбрать файл'}
                </label>
              </div>
            </div>
          )}

          <div className="control-group button-group">
            <button 
              className={`analyze-button ${loading ? 'loading' : ''}`}
              onClick={handleAnalyze} 
              disabled={loading || !tzFile || !docFile}
            >
              {loading ? (
                <>
                  <span className="spinner"></span>
                  Анализ в процессе...
                </>
              ) : (
                'Выполнить анализ'
              )}
            </button>
          </div>
        </div>

        {error && (
          <div className="error-message">
            <span className="error-icon">⚠️</span>
            <span className="error-text">{error}</span>
          </div>
        )}

        {loading && (
          <div className="progress-container">
            <div className="progress-header">
              <span className="progress-title">🔄 Анализ в процессе</span>
              <span className="progress-percentage">{analysisProgress}%</span>
            </div>
            
            <div className="progress-bar">
              <div 
                className="progress-fill" 
                style={{ 
                  width: `${analysisProgress}%`,
                  background: analysisProgress < 30 
                    ? 'linear-gradient(90deg, #3b82f6, #60a5fa)'
                    : analysisProgress < 70 
                    ? 'linear-gradient(90deg, #8b5cf6, #a78bfa)'
                    : 'linear-gradient(90deg, #10b981, #34d399)'
                }}
              >
                <div className="progress-shimmer"></div>
              </div>
            </div>
            
            {currentStage && (
              <div className="progress-stage">
                <span className="stage-icon">📊</span>
                <span className="stage-text">{currentStage}</span>
              </div>
            )}
            
            <div className="progress-info">
              <small>Это может занять несколько минут. Пожалуйста, не закрывайте страницу.</small>
            </div>
          </div>
        )}
      </div>
    </header>
  );
};

export default Header;
