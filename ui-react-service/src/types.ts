
export interface Requirement {
    number: number;
    requirement: string;
    status: string;
    confidence: number;
    solution_description: string;
    reference: string;
    evidence_text?: string;  // Конкретный текст с листа для поиска
    discrepancies: string;
    section?: string;
  }
  