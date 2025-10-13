import React, { useState } from 'react';
import './App.css';
import Header from './components/Header';
import RequirementList from './components/RequirementList';
import PdfViewer from './components/PdfViewer';
import RequirementEditor, { EditableRequirement } from './components/RequirementEditor';
import ResizablePanels from './components/ResizablePanels';
import EmptyState from './components/EmptyState';
import { Requirement } from './types';
import { useLocalStorage } from './hooks/useLocalStorage';
import { useNotification } from './hooks/useNotification';
import { STORAGE_KEYS, MESSAGES, TIMEOUTS } from './constants';

interface AppState {
  currentStep: 1 | 2;
  confirmedRequirements: EditableRequirement[] | null;
  requirements: Requirement[];
  summary: string;
  sheetToPdfMapping: Record<string, number>;
  analysisCompleted: boolean;
}

const initialAppState: AppState = {
  currentStep: 1,
  confirmedRequirements: null,
  requirements: [],
  summary: '',
  sheetToPdfMapping: {},
  analysisCompleted: false,
};

function App() {
  // Локальное состояние (не сохраняется)
  const [extractedRequirements, setExtractedRequirements] = useState<EditableRequirement[] | null>(null);
  const [showRequirementEditor, setShowRequirementEditor] = useState(false);
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [selectedPage, setSelectedPage] = useState<number | null>(null);
  const [highlightText, setHighlightText] = useState<string>('');
  const [pageChangeKey, setPageChangeKey] = useState<number>(0);

  // Система уведомлений
  const { notification, showNotification, hideNotification } = useNotification();

  // Персистентное состояние в localStorage
  const { storedValue: appState, setStoredValue: setAppState, clearStorage } = useLocalStorage<AppState>({
    key: STORAGE_KEYS.APP_DATA,
    initialValue: initialAppState,
    onRestore: (data) => {
      console.log('📦 Восстановлены данные из localStorage:', data);
      const hasResults = data.requirements && data.requirements.length > 0;
      showNotification(
        hasResults
          ? `📦 Восстановлены результаты анализа (${data.requirements.length} требований). Загрузите PDF проекта для просмотра чертежей.`
          : '📦 Восстановлено предыдущее состояние приложения',
        TIMEOUTS.NOTIFICATION_LONG
      );
    },
  });

  // Шаг 1: Обработка извлеченных требований
  const handleRequirementsExtracted = (reqs: EditableRequirement[]) => {
    setExtractedRequirements(reqs);
    setShowRequirementEditor(true);
  };

  // Подтверждение требований и переход к шагу 2
  const handleRequirementsConfirmed = (reqs: EditableRequirement[]) => {
    setAppState({
      ...appState,
      confirmedRequirements: reqs,
      currentStep: 2,
    });
    setShowRequirementEditor(false);
  };

  // Отмена редактирования
  const handleRequirementsCancel = () => {
    setShowRequirementEditor(false);
    setExtractedRequirements(null);
  };

  // Шаг 2: Завершение анализа
  const handleAnalysisComplete = (
    newRequirements: Requirement[],
    newSummary: string,
    mapping?: Record<string, number>
  ) => {
    setAppState({
      ...appState,
      requirements: newRequirements,
      summary: newSummary,
      analysisCompleted: true,
      sheetToPdfMapping: mapping || appState.sheetToPdfMapping,
    });
    
    if (mapping) {
      console.log('📊 Получен mapping листов:', mapping);
    }
  };

  const handleDocFileChange = (file: File | null) => {
    setPdfFile(file);
    setSelectedPage(null);
    setHighlightText('');
  };

  const handleRequirementSelect = (page: number, textToHighlight?: string) => {
    setSelectedPage(page);
    setHighlightText(textToHighlight || '');
    setPageChangeKey(prev => prev + 1);
  };

  // Сброс к шагу 1 (начать заново)
  const handleReset = () => {
    if (!window.confirm(MESSAGES.CONFIRM.RESET)) return;

    // Сбрасываем локальное состояние
    setExtractedRequirements(null);
    setPdfFile(null);
    setSelectedPage(null);
    setHighlightText('');

    // Очищаем localStorage и персистентное состояние
    try {
      clearStorage();
      showNotification(MESSAGES.SUCCESS.STORAGE_CLEANUP, TIMEOUTS.NOTIFICATION_SHORT);
    } catch (error) {
      console.error('⚠️ Ошибка очистки localStorage:', error);
      showNotification(MESSAGES.ERROR.STORAGE_CLEANUP, TIMEOUTS.NOTIFICATION_SHORT);
    }
  };

  const selectedRequirementsCount = appState.confirmedRequirements?.filter(r => r.selected).length || 0;

  // Компонент Header
  const headerContent = (
    <Header 
      onRequirementsExtracted={handleRequirementsExtracted}
      onAnalysisComplete={handleAnalysisComplete}
      onDocFileChange={handleDocFileChange}
      confirmedRequirements={appState.confirmedRequirements}
      analysisCompleted={appState.analysisCompleted}
      onReset={handleReset}
    />
  );

  // Левая панель (требования)
  const leftPanelContent = (
    <div className="panel-content">
      {appState.currentStep === 1 ? (
        <EmptyState
          icon="📋"
          text="Загрузите ТЗ для начала работы"
          hint="Требования будут извлечены и показаны для редактирования"
        />
      ) : appState.requirements.length > 0 ? (
        <RequirementList
          requirements={appState.requirements}
          onSelect={handleRequirementSelect}
          sheetToPdfMapping={appState.sheetToPdfMapping}
        />
      ) : (
        <EmptyState
          icon="📊"
          text="Загрузите проектную документацию"
          hint={`Проект будет проверен по ${selectedRequirementsCount} требованиям`}
        />
      )}
    </div>
  );

  // Правая панель (PDF + сводка)
  const rightPanelContent = (
    <div className="panel-content">
      {appState.requirements.length > 0 && !pdfFile ? (
        <EmptyState
          className="empty-state pdf-missing-state"
          icon="📄"
          text="PDF файл проекта не загружен"
          hint="Результаты анализа восстановлены из localStorage, но PDF файл необходимо загрузить повторно для просмотра чертежей."
          action="↑ Загрузите проектную документацию в верхней панели"
        />
      ) : (
        <PdfViewer
          file={pdfFile}
          page={selectedPage}
          highlightText={highlightText}
          key={pageChangeKey}
        />
      )}
      {appState.summary && (
        <div className="summary-container">
          <h3>Общая сводка</h3>
          <pre>{appState.summary}</pre>
          <button className="btn-reset" onClick={handleReset}>
            🔄 Начать заново
          </button>
        </div>
      )}
    </div>
  );

  return (
    <div className="App">
      <ResizablePanels
        header={headerContent}
        leftPanel={leftPanelContent}
        rightPanel={rightPanelContent}
      />

      {/* Модальное окно редактора требований */}
      {showRequirementEditor && extractedRequirements && (
        <RequirementEditor
          requirements={extractedRequirements}
          onConfirm={handleRequirementsConfirmed}
          onCancel={handleRequirementsCancel}
        />
      )}

      {/* Уведомление */}
      {notification && (
        <div className="notification">
          <div className="notification-content">
            <span className="notification-icon">💾</span>
            <span className="notification-text">{notification}</span>
            <button
              className="notification-close"
              onClick={hideNotification}
              aria-label="Закрыть уведомление"
            >
              ✕
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;