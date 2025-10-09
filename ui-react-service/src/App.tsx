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

  const handleAnalysisComplete = (
    newRequirements: Requirement[],
    newSummary: string,
    file: File
  ) => {
    setRequirements(newRequirements);
    setSummary(newSummary);
    setPdfFile(file);
  };

  const handleRequirementSelect = (page: number) => {
    setSelectedPage(page);
  };

  return (
    <div className="App">
      <Header onAnalysisComplete={handleAnalysisComplete} />
      <main className="App-main">
        <div className="left-panel">
          <RequirementList
            requirements={requirements}
            onSelect={handleRequirementSelect}
          />
        </div>
        <div className="right-panel">
          <PdfViewer file={pdfFile} page={selectedPage} />
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