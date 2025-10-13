
import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { Requirement } from '../types';
import { EditableRequirement } from './RequirementEditor';
import FileUpload from './FileUpload';
import StageSelector from './StageSelector';
import { API_URL, TIMEOUTS, MESSAGES, STAGE_ICONS } from '../constants';
import { formatApiError } from '../utils/errorFormatter';
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
  analysisCompleted?: boolean;
  onReset?: () => void;
}

const Header: React.FC<HeaderProps> = ({ 
  onRequirementsExtracted,
  onAnalysisComplete, 
  onDocFileChange,
  confirmedRequirements,
  analysisCompleted = false,
  onReset
}) => {
  const [stage, setStage] = useState('ФЭ');
  const [tzFile, setTzFile] = useState<File | null>(null);
  const [docFile, setDocFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analysisProgress, setAnalysisProgress] = useState(0);
  const [realTimeStatus, setRealTimeStatus] = useState<any>(null);
  const [pollingErrors, setPollingErrors] = useState(0);
  const statusPollingRef = useRef<NodeJS.Timeout | null>(null);

  // Определяем текущий шаг: 1 - извлечение требований, 2 - анализ
  const currentStep = confirmedRequirements ? 2 : 1;

  // Функция для получения статуса
  const fetchStatus = async (endpoint: string) => {
    try {
      const response = await axios.get(`${API_URL}/${endpoint}`);
      const data = response.data;
      
      setRealTimeStatus(data);
      setAnalysisProgress(data.progress || 0);
      setPollingErrors(0); // Сброс счётчика ошибок
    } catch (err) {
      console.error('Status fetch error:', err);
      setPollingErrors(prev => prev + 1);
      
      // Останавливаем polling после 10 неудачных попыток (20 секунд)
      if (pollingErrors >= 10) {
        if (statusPollingRef.current) {
          clearInterval(statusPollingRef.current);
          statusPollingRef.current = null;
        }
        setError('Потеряно соединение с сервером. Пожалуйста, обновите страницу.');
      }
    }
  };

  // Polling статуса анализа
  useEffect(() => {
    if (loading) {
      const endpoint = currentStep === 1 ? 'extraction_status' : 'status';
      statusPollingRef.current = setInterval(() => fetchStatus(endpoint), TIMEOUTS.STATUS_POLLING);
    } else {
      if (statusPollingRef.current) {
        clearInterval(statusPollingRef.current);
        statusPollingRef.current = null;
      }
      setRealTimeStatus(null);
      setAnalysisProgress(0);
      setPollingErrors(0);
    }

    return () => {
      if (statusPollingRef.current) {
        clearInterval(statusPollingRef.current);
      }
    };
  }, [loading, currentStep]);

  // Общая функция для подготовки к запросу
  const prepareForRequest = () => {
    setLoading(true);
    setError(null);
    setAnalysisProgress(0);
    setPollingErrors(0);
  };

  // Шаг 1: Извлечение требований из ТЗ
  const handleExtractRequirements = async () => {
    if (!tzFile) {
      setError(MESSAGES.ERROR.TZ_FILE_REQUIRED);
      return;
    }

    prepareForRequest();
    const formData = new FormData();
    formData.append('tz_document', tzFile);

    try {
      const response = await axios.post(`${API_URL}/extract_requirements`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: TIMEOUTS.REQUIREMENTS_EXTRACTION,
      });

      onRequirementsExtracted(response.data.requirements);
    } catch (err) {
      setError(formatApiError(err, MESSAGES.ERROR.REQUIREMENTS_EXTRACTION));
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  // Шаг 2: Анализ проектной документации
  const handleAnalyzeProject = async () => {
    if (!docFile || !confirmedRequirements) {
      setError(MESSAGES.ERROR.DOC_FILE_REQUIRED);
      return;
    }

    prepareForRequest();
    const formData = new FormData();
    formData.append('stage', stage);
    formData.append('requirements_json', JSON.stringify(confirmedRequirements));
    formData.append('doc_document', docFile);

    try {
      const response = await axios.post(`${API_URL}/analyze`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: TIMEOUTS.PROJECT_ANALYSIS,
      });

      const { requirements, summary, sheet_to_pdf_mapping } = response.data;
      console.log('📄 Получены данные анализа:', { requirements: requirements.length, mapping: sheet_to_pdf_mapping });
      onAnalysisComplete(requirements, summary, sheet_to_pdf_mapping);
    } catch (err) {
      setError(formatApiError(err, MESSAGES.ERROR.PROJECT_ANALYSIS));
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  // Показываем кнопку очистки если есть сохраненные данные
  const hasStoredData = confirmedRequirements !== null || analysisCompleted;

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
        
        {/* Кнопка очистки данных */}
        {hasStoredData && onReset && !loading && (
          <button 
            className="btn-clear-data"
            onClick={onReset}
            title="Очистить все данные и начать заново"
          >
            🗑️ Очистить всё
          </button>
        )}
        
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
                onChange={(file) => {
                  setDocFile(file);
                  onDocFileChange(file); // Передаем файл в App для отображения
                }}
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

            {/* Показываем статус если доступен */}
            {realTimeStatus && realTimeStatus.stage_name && (
              <div className="progress-stage">
                <span className="stage-icon">
                  {STAGE_ICONS[realTimeStatus.current_stage as keyof typeof STAGE_ICONS] || '📊'}
                </span>
                <span className="stage-text">
                  Этап {realTimeStatus.current_stage}/{realTimeStatus.total_stages}: {realTimeStatus.stage_name}
                </span>
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
