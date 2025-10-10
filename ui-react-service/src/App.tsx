import React, { useState } from 'react';
import './App.css';
import Header from './components/Header';
import RequirementList from './components/RequirementList';
import PdfViewer from './components/PdfViewer';
import { Requirement } from './types';

function App() {
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [summary, setSummary] = useState<string>('');
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [selectedPage, setSelectedPage] = useState<number | null>(null);
  const [highlightText, setHighlightText] = useState<string>('');
  const [pageChangeKey, setPageChangeKey] = useState<number>(0);

  const handleAnalysisComplete = (
    newRequirements: Requirement[],
    newSummary: string
  ) => {
    setRequirements(newRequirements);
    setSummary(newSummary);
  };

  const handleDocFileChange = (file: File | null) => {
    setPdfFile(file);
    setSelectedPage(null);
    setHighlightText(''); // Сброс highlight при загрузке нового файла
  };

  const handleRequirementSelect = (page: number, textToHighlight?: string) => {
    // Форсируем перерасчет через key change
    setSelectedPage(page);
    setHighlightText(textToHighlight || '');
    setPageChangeKey(prev => prev + 1);
  };

  return (
    <div className="App">
      <Header 
        onAnalysisComplete={handleAnalysisComplete}
        onDocFileChange={handleDocFileChange}
      />
      <main className="App-main">
        <div className="left-panel">
          <RequirementList
            requirements={requirements}
            onSelect={handleRequirementSelect}
          />
        </div>
        <div className="right-panel">
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
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

export default App;