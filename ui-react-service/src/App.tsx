import React, { useState } from 'react';
import './App.css';
import Header from './components/Header';
import RequirementList from './components/RequirementList';
import PdfViewer from './components/PdfViewer';
import RequirementEditor, { EditableRequirement } from './components/RequirementEditor';
import ResizablePanels from './components/ResizablePanels';
import { Requirement } from './types';

function App() {
  // Состояние для двухшагового процесса
  const [currentStep, setCurrentStep] = useState<1 | 2>(1);
  
  // Шаг 1: Извлеченные требования для редактирования
  const [extractedRequirements, setExtractedRequirements] = useState<EditableRequirement[] | null>(null);
  const [showRequirementEditor, setShowRequirementEditor] = useState(false);
  
  // Шаг 2: Подтвержденные требования для анализа
  const [confirmedRequirements, setConfirmedRequirements] = useState<EditableRequirement[] | null>(null);
  
  // Результаты анализа
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [summary, setSummary] = useState<string>('');
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [selectedPage, setSelectedPage] = useState<number | null>(null);
  const [highlightText, setHighlightText] = useState<string>('');
  const [pageChangeKey, setPageChangeKey] = useState<number>(0);
  const [analysisCompleted, setAnalysisCompleted] = useState(false);
  
  // Mapping номеров листов на чертежах → порядковые номера страниц в PDF
  const [sheetToPdfMapping, setSheetToPdfMapping] = useState<Record<string, number>>({});

  // Шаг 1: Обработка извлеченных требований
  const handleRequirementsExtracted = (reqs: EditableRequirement[]) => {
    setExtractedRequirements(reqs);
    setShowRequirementEditor(true);
  };

  // Подтверждение требований и переход к шагу 2
  const handleRequirementsConfirmed = (reqs: EditableRequirement[]) => {
    setConfirmedRequirements(reqs);
    setShowRequirementEditor(false);
    setCurrentStep(2);
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
    setRequirements(newRequirements);
    setSummary(newSummary);
    setAnalysisCompleted(true); // Устанавливаем флаг завершения анализа
    if (mapping) {
      setSheetToPdfMapping(mapping);
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
    setCurrentStep(1);
    setExtractedRequirements(null);
    setConfirmedRequirements(null);
    setRequirements([]);
    setSummary('');
    setPdfFile(null);
    setSelectedPage(null);
    setHighlightText('');
    setSheetToPdfMapping({});
    setAnalysisCompleted(false); // Сбрасываем флаг завершения анализа
  };

  // Компонент Header
  const headerContent = (
    <Header 
      onRequirementsExtracted={handleRequirementsExtracted}
      onAnalysisComplete={handleAnalysisComplete}
      onDocFileChange={handleDocFileChange}
      confirmedRequirements={confirmedRequirements}
      analysisCompleted={analysisCompleted}
    />
  );

  // Левая панель (требования)
  const leftPanelContent = (
    <div className="panel-content">
      {currentStep === 1 ? (
        <div className="empty-state">
          <div className="empty-icon">📋</div>
          <p className="empty-text">Загрузите ТЗ для начала работы</p>
          <p className="empty-hint">
            Требования будут извлечены и показаны для редактирования
          </p>
        </div>
      ) : requirements.length > 0 ? (
        <RequirementList
          requirements={requirements}
          onSelect={handleRequirementSelect}
          sheetToPdfMapping={sheetToPdfMapping}
        />
      ) : (
        <div className="empty-state">
          <div className="empty-icon">📊</div>
          <p className="empty-text">Загрузите проектную документацию</p>
          <p className="empty-hint">
            Проект будет проверен по {confirmedRequirements?.filter(r => r.selected).length} требованиям
          </p>
        </div>
      )}
    </div>
  );

  // Правая панель (PDF + сводка)
  const rightPanelContent = (
    <div className="panel-content">
      <PdfViewer 
        file={pdfFile} 
        page={selectedPage} 
        highlightText={highlightText}
        key={pageChangeKey}
      />
      {summary && (
        <div className="summary-container">
          <h3>Общая сводка</h3>
          <pre>{summary}</pre>
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
    </div>
  );
}

export default App;