export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type DocType = "term_sheet" | "appraisal" | "rehab_budget" | "draw_request" | "other";

export interface Fields {
  doc_type: DocType;
  borrower_name: string | null;
  property_address: string | null;
  purchase_price: number | null;
  loan_amount: number | null;
  interest_rate_pct: number | null;
  term_months: number | null;
  origination_points: number | null;
  as_is_value: number | null;
  after_repair_value: number | null;
  rehab_budget_total: number | null;
  draw_number: number | null;
  draw_amount_requested: number | null;
}

export interface DocumentOut {
  id: string;
  filename: string;
  page_count: number;
  fields: Fields;
}

export interface Flag {
  code: string;
  severity: "warning" | "info";
  message: string;
}

export interface LoanFile {
  id: string;
  name: string;
  is_sample: boolean;
  expires_at: string | null;
  documents: DocumentOut[];
  flags: Flag[];
}

export interface LoanFileSummary {
  id: string;
  name: string;
  document_count: number;
}

export interface Citation {
  source: string;
  title: string;
  cited_text: string;
}

export interface AnswerOut {
  answer: string;
  citations: Citation[];
  sources_searched: string[];
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init);
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // keep the generic message
    }
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  samples: () => request<LoanFileSummary[]>("/loan-files/samples"),
  loanFile: (id: string) => request<LoanFile>(`/loan-files/${id}`),
  createLoanFile: (name: string) =>
    request<LoanFile>("/loan-files", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),
  upload: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentOut>(`/loan-files/${id}/documents`, { method: "POST", body: form });
  },
  ask: (id: string, question: string) =>
    request<AnswerOut>(`/loan-files/${id}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    }),
};
