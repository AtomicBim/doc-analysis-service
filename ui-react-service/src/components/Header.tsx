
import React, { useState } from 'react';
import axios from 'axios';
import { Requirement } from '../types';
import { EditableRequirement } from './RequirementEditor';
import FileUpload from './FileUpload';
import StageSelector from './StageSelector';
import './Header.css';

interface HeaderProps {
  onRequirementsExtracted: (requirements: EditableRequirement[]) => void;
  onAnalysisComplete: (
    requirements: Requirement[],
    summary: string,
    sheetToPdfMapping?: Record<string, number>
  ) => void;
  onDocFileChange: (file: File | null) => void;
  confirmedRequirements: EditableRequirement[] | null;
  analysisCompleted?: boolean; // Флаг завершения анализа
}

const API_URL = '/api';

const Header: React.FC<HeaderProps> = ({ 
  onRequirementsExtracted,
  onAnalysisComplete, 
  onDocFileChange,
  confirmedRequirements,
  analysisCompleted = false
}) => {
  const [stage, setStage] = useState('ФЭ');
  const [tzFile, setTzFile] = useState<File | null>(null);
  const [docFile, setDocFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analysisProgress, setAnalysisProgress] = useState(0);
  const [currentStage, setCurrentStage] = useState('');
  
  // Определяем текущий шаг: 1 - извлечение требований, 2 - анализ
  const currentStep = confirmedRequirements ? 2 : 1;

  // Шаг 1: Извлечение требований из ТЗ
  const handleExtractRequirements = async () => {
    if (!tzFile) {
      setError('Необходимо загрузить ТЗ.');
      return;
    }

    setLoading(true);
    setError(null);
    setAnalysisProgress(0);
    setCurrentStage('');

    const stages = [
      { name: 'Извлечение текста из ТЗ', duration: 15000, progress: 50 },
      { name: 'Сегментация требований', duration: 10000, progress: 95 },
    ];

    let currentStageIndex = 0;
    let elapsed = 0;
    const tick = 500;
    const progressInterval = setInterval(() => {
      if (currentStageIndex < stages.length) {
        const stage = stages[currentStageIndex];
        elapsed += tick;
        setCurrentStage(stage.name);
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
    formData.append('tz_document', tzFile);

    try {
      const response = await axios.post(`${API_URL}/extract_requirements`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        timeout: 300000, // 5 minutes
      });

      clearInterval(progressInterval);
      setAnalysisProgress(100);
      setCurrentStage('Завершено');

      const { requirements } = response.data;
      onRequirementsExtracted(requirements);
    } catch (err: any) {
      clearInterval(progressInterval);
      let errorMessage = 'Произошла ошибка при извлечении требований.';
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

  // Шаг 2: Анализ проектной документации
  const handleAnalyzeProject = async () => {
    if (!docFile || !confirmedRequirements) {
      setError('Необходимо загрузить проектную документацию и подтвердить требования.');
      return;
    }

    setLoading(true);
    setError(null);
    setAnalysisProgress(0);
    setCurrentStage('');

    const stages = [
      { name: 'Stage 1: Извлечение метаданных', duration: 20000, progress: 33 },
      { name: 'Stage 2: Оценка релевантности', duration: 30000, progress: 66 },
      { name: 'Stage 3: Детальный анализ и генерация отчета', duration: 240000, progress: 95 },
    ];

    let currentStageIndex = 0;
    let elapsed = 0;
    const tick = 500;
    const progressInterval = setInterval(() => {
      if (currentStageIndex < stages.length) {
        const stage = stages[currentStageIndex];
        elapsed += tick;
        setCurrentStage(stage.name);

        // Вычисляем прогресс для текущей стадии: от предыдущего процента до текущего
        const prevProgress = currentStageIndex > 0 ? stages[currentStageIndex - 1].progress : 0;
        const stageRange = stage.progress - prevProgress;
        const stageElapsed = Math.min(elapsed / stage.duration, 1.0);
        const currentProgress = prevProgress + (stageRange * stageElapsed);

        setAnalysisProgress(Math.min(currentProgress, 95));

        console.log(`📊 Stage ${currentStageIndex + 1}/${stages.length}: ${stage.name} - Progress: ${currentProgress.toFixed(1)}%`);

        if (elapsed >= stage.duration) {
          currentStageIndex++;
          elapsed = 0;
        }
      }
    }, tick);

    const formData = new FormData();
    formData.append('stage', stage);
    formData.append('requirements_json', JSON.stringify(confirmedRequirements));
    formData.append('doc_document', docFile);

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

      const { requirements, summary, sheet_to_pdf_mapping } = response.data;
      console.log('📄 Получены данные анализа:', { requirements: requirements.length, mapping: sheet_to_pdf_mapping });
      onAnalysisComplete(requirements, summary, sheet_to_pdf_mapping);
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
          <p className="header-subtitle">
            {currentStep === 1 
              ? 'Шаг 1: Извлечение требований из ТЗ' 
              : `Шаг 2: Анализ проектной документации (${confirmedRequirements?.filter(r => r.selected).length} требований)`}
          </p>
        </div>
        
        {/* Индикатор шагов */}
        <div className="steps-indicator">
          <div className={`step ${currentStep >= 1 ? 'active' : ''} ${currentStep > 1 ? 'completed' : ''}`}>
            <div className="step-number">{currentStep > 1 ? '✓' : '1'}</div>
            <div className="step-label">Извлечение требований</div>
          </div>
          <div className="step-divider"></div>
          <div className={`step ${currentStep >= 2 ? 'active' : ''} ${analysisCompleted ? 'completed' : ''}`}>
            <div className="step-number">{analysisCompleted ? '✓' : '2'}</div>
            <div className="step-label">Анализ проекта</div>
          </div>
        </div>
        
        <div className="controls-grid">
          {/* Шаг 1: Загрузка ТЗ */}
          {currentStep === 1 && (
            <>
              <FileUpload
                label="Техническое задание (ТЗ)"
                accept=".pdf,.docx"
                fileName={tzFile?.name}
                onChange={setTzFile}
              />

              <div className="control-group button-group">
                <button 
                  className={`analyze-button ${loading ? 'loading' : ''}`}
                  onClick={handleExtractRequirements} 
                  disabled={loading || !tzFile}
                >
                  {loading ? (
                    <>
                      <span className="spinner"></span>
                      Извлечение требований...
                    </>
                  ) : (
                    '📋 Извлечь требования из ТЗ'
                  )}
                </button>
              </div>
            </>
          )}

          {/* Шаг 2: Загрузка проектной документации */}
          {currentStep === 2 && (
            <>
              <StageSelector
                value={stage}
                onChange={setStage}
                disabled={loading}
              />

              <FileUpload
                label="Проектная документация"
                accept=".pdf"
                fileName={docFile?.name}
                onChange={setDocFile}
                disabled={loading}
              />

              <div className="control-group button-group">
                <button 
                  className={`analyze-button ${loading ? 'loading' : ''}`}
                  onClick={handleAnalyzeProject} 
                  disabled={loading || !docFile}
                >
                  {loading ? (
                    <>
                      <span className="spinner"></span>
                      Анализ в процессе...
                    </>
                  ) : (
                    '🔍 Выполнить анализ проекта'
                  )}
                </button>
              </div>
            </>
          )}
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
