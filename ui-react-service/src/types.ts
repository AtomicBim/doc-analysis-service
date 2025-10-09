
export interface Requirement {
    number: number;
    requirement: string;
    status: string;
    confidence: number;
    solution_description: string;
    reference: string;
    discrepancies: string;
    recommendations: string;
    section?: string;
    trace_id?: string;
  }
  