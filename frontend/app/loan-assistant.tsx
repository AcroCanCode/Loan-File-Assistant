"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, type AnswerOut, type DocumentOut, type Fields, type LoanFile, type LoanFileSummary } from "@/lib/api";

const UPLOAD_KEY = "lfa-upload-file-id";
const SAMPLE_FOLDERS: Record<string, string> = {
  "1407 Pecan Hollow Dr (fix and flip)": "L1",
  "902 Larkspur Ct (three draws)": "L2",
  "55 Cedar Bend Ln (second-story addition)": "L3",
  "3318 Willow Run (light rehab)": "L4",
};
const SUGGESTED = [
  "How much has been drawn so far, and how much of the rehab budget is left?",
  "What is the after-repair value, and what is the loan-to-ARV?",
  "Does any draw include work that isn't in the original budget?",
  "Who is the borrower and who guarantees the loan?",
];
const DOC_LABELS: Record<Fields["doc_type"], string> = {
  term_sheet: "Term sheet",
  appraisal: "Appraisal",
  rehab_budget: "Rehab budget",
  draw_request: "Draw request",
  other: "Other",
};

function readUploadId(): string | null {
  try {
    return localStorage.getItem(UPLOAD_KEY);
  } catch {
    return null; // storage unavailable: uploads just won't be remembered
  }
}

function rememberUploadId(id: string) {
  try {
    localStorage.setItem(UPLOAD_KEY, id);
  } catch {
    // ignore
  }
}

function forgetUploadId() {
  try {
    localStorage.removeItem(UPLOAD_KEY);
  } catch {
    // ignore
  }
}

const money = (n: number | null) => (n == null ? "—" : `$${n.toLocaleString("en-US")}`);

function first<K extends keyof Fields>(docs: DocumentOut[], key: K, type?: Fields["doc_type"]): Fields[K] | null {
  for (const d of docs) {
    if (type && d.fields.doc_type !== type) continue;
    if (d.fields[key] != null) return d.fields[key];
  }
  return null;
}

function keyFields(f: Fields): [string, string][] {
  switch (f.doc_type) {
    case "term_sheet":
      return [
        ["Loan", money(f.loan_amount)],
        ["Rate", f.interest_rate_pct == null ? "—" : `${f.interest_rate_pct}%`],
        ["Term", f.term_months == null ? "—" : `${f.term_months} mo`],
        ["Points", f.origination_points == null ? "—" : `${f.origination_points}`],
        ["Purchase", money(f.purchase_price)],
      ];
    case "appraisal":
      return [
        ["As is", money(f.as_is_value)],
        ["After repair", money(f.after_repair_value)],
      ];
    case "rehab_budget":
      return [["Budget", money(f.rehab_budget_total)]];
    case "draw_request":
      return [
        ["Draw", f.draw_number == null ? "—" : `#${f.draw_number}`],
        ["Requested", money(f.draw_amount_requested)],
      ];
    default:
      return [];
  }
}

export default function LoanAssistant() {
  const [samples, setSamples] = useState<LoanFileSummary[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [loanFile, setLoanFile] = useState<LoanFile | null>(null);
  const [uploadId, setUploadId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [slow, setSlow] = useState(false);

  const load = useCallback(async (id: string) => {
    try {
      setLoanFile(await api.loanFile(id));
    } catch (e) {
      setLoanFile(null);
      if (e instanceof ApiError && e.status === 404 && id === readUploadId()) {
        // The private upload expired: start over.
        forgetUploadId();
        setUploadId(null);
        setSelected("new");
      }
    }
  }, []);

  const select = useCallback(
    (id: string) => {
      setSelected(id);
      setLoanFile(null);
      if (id !== "new") load(id);
    },
    [load],
  );

  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), 5000);
    api
      .samples()
      .then((list) => {
        setSamples(list);
        setUploadId(readUploadId());
        if (list[0]) select(list[0].id);
      })
      .catch(() => setError("Couldn't reach the API. It may be waking up; reload in a minute."))
      .finally(() => clearTimeout(timer));
    return () => clearTimeout(timer);
  }, [select]);

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6">
      <header className="mb-6">
        <p className="text-xs font-semibold uppercase tracking-wider text-accent">Bridge lending · AI demo</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">Loan File Assistant</h1>
        <p className="mt-2 max-w-3xl text-muted">
          Reads the documents in a fix-and-flip loan file, pulls out the terms, flags underwriting issues, and answers
          questions with citations to the page it found the answer on.
        </p>
        <p className="mt-3 inline-block rounded-md bg-warn-soft px-3 py-1.5 text-sm text-warn">
          Every document here is fictional sample data. Don&apos;t upload real borrower information.
        </p>
      </header>

      {error && <p className="rounded-lg border border-line bg-surface p-4">{error}</p>}
      {!samples && !error && (
        <p className="text-muted">Loading{slow ? " — the server is waking up, this can take up to a minute…" : "…"}</p>
      )}

      {samples && (
        <nav className="mb-6 flex flex-wrap gap-2" aria-label="Loan files">
          {samples.map((s) => (
            <TabButton key={s.id} active={selected === s.id} onClick={() => select(s.id)}>
              {s.name}
            </TabButton>
          ))}
          <TabButton active={selected === uploadId && uploadId !== null} onClick={() => select(uploadId ?? "new")}>
            Upload your own
          </TabButton>
        </nav>
      )}

      {selected === "new" ? (
        <NewUpload
          onCreated={(id) => {
            rememberUploadId(id);
            setUploadId(id);
            select(id);
          }}
        />
      ) : (
        loanFile && <LoanFileView key={loanFile.id} loanFile={loanFile} onChanged={() => load(loanFile.id)} />
      )}

      <footer className="mt-12 border-t border-line pt-4 text-sm text-muted">
        Claude extracts fields with structured outputs and answers from passages retrieved with pgvector. Flags are
        plain code checks against the extracted numbers, so they&apos;re repeatable.
      </footer>
    </div>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-full border px-3.5 py-1.5 text-sm transition ${
        active ? "border-accent bg-accent-soft font-medium text-accent" : "border-line bg-surface hover:border-accent"
      }`}
    >
      {children}
    </button>
  );
}

const DOC_ORDER: Fields["doc_type"][] = ["term_sheet", "appraisal", "rehab_budget", "draw_request", "other"];

function LoanFileView({ loanFile, onChanged }: { loanFile: LoanFile; onChanged: () => void }) {
  const docs = [...loanFile.documents].sort(
    (a, b) =>
      DOC_ORDER.indexOf(a.fields.doc_type) - DOC_ORDER.indexOf(b.fields.doc_type) ||
      (a.fields.draw_number ?? 0) - (b.fields.draw_number ?? 0) ||
      a.filename.localeCompare(b.filename),
  );
  const loan = first(docs, "loan_amount", "term_sheet") ?? first(docs, "loan_amount");
  const arv = first(docs, "after_repair_value", "appraisal") ?? first(docs, "after_repair_value");
  const budget = first(docs, "rehab_budget_total", "rehab_budget") ?? first(docs, "rehab_budget_total");
  const drawn = docs
    .filter((d) => d.fields.doc_type === "draw_request")
    .reduce((sum, d) => sum + (d.fields.draw_amount_requested ?? 0), 0);
  const folder = SAMPLE_FOLDERS[loanFile.name];

  return (
    <div className="grid gap-6 lg:grid-cols-5">
      <section className="space-y-6 lg:col-span-3">
        <div className="rounded-xl border border-line bg-surface p-5">
          <h2 className="text-lg font-semibold">{first(docs, "property_address") ?? loanFile.name}</h2>
          <p className="text-sm text-muted">{first(docs, "borrower_name") ?? "Borrower not found yet"}</p>
          <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Stat label="Loan amount" value={money(loan)} />
            <Stat label="After-repair value" value={money(arv)} />
            <Stat label="Loan to ARV" value={loan && arv ? `${((loan / arv) * 100).toFixed(1)}%` : "—"} />
            <Stat label="Drawn / budget" value={budget ? `${money(drawn)} / ${money(budget)}` : money(drawn)} />
          </dl>
          <ul className="mt-4 space-y-2">
            {loanFile.flags.length === 0 && docs.length > 0 && (
              <li className="text-sm text-muted">No issues found by the underwriting checks.</li>
            )}
            {loanFile.flags.map((f) => (
              <li
                key={f.code}
                className={`rounded-md px-3 py-2 text-sm ${f.severity === "warning" ? "bg-warn-soft text-warn" : "bg-accent-soft"}`}
              >
                {f.severity === "warning" ? "⚠ " : ""}
                {f.message}
              </li>
            ))}
          </ul>
        </div>

        <div className="rounded-xl border border-line bg-surface">
          <h2 className="border-b border-line px-5 py-3 font-semibold">Documents and extracted fields</h2>
          {docs.length === 0 && <p className="px-5 py-4 text-sm text-muted">No documents yet.</p>}
          <ul className="divide-y divide-line">
            {docs.map((d) => (
              <li key={d.id} className="flex flex-col gap-2 px-5 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <span className="font-medium">{DOC_LABELS[d.fields.doc_type]}</span>{" "}
                  {folder ? (
                    <a className="text-sm text-accent underline" href={`/samples/${folder}/${d.filename}`} target="_blank">
                      {d.filename}
                    </a>
                  ) : (
                    <span className="text-sm text-muted">{d.filename}</span>
                  )}
                </div>
                <dl className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
                  {keyFields(d.fields).map(([k, v]) => (
                    <div key={k} className="flex gap-1">
                      <dt className="text-muted">{k}</dt>
                      <dd className="font-medium tabular-nums">{v}</dd>
                    </div>
                  ))}
                </dl>
              </li>
            ))}
          </ul>
        </div>

        {!loanFile.is_sample && <Uploader loanFileId={loanFile.id} count={docs.length} onUploaded={onChanged} />}
      </section>

      <section className="lg:col-span-2">
        <Ask loanFileId={loanFile.id} disabled={docs.length === 0} />
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-0.5 font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

function Ask({ loanFileId, disabled }: { loanFileId: string; disabled: boolean }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AnswerOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (q: string) => {
    if (q.trim().length < 3) return;
    setQuestion(q);
    setBusy(true);
    setError(null);
    setAnswer(null);
    try {
      setAnswer(await api.ask(loanFileId, q));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-line bg-surface p-5 lg:sticky lg:top-6">
      <h2 className="font-semibold">Ask about this loan file</h2>
      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          submit(question);
        }}
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={500}
          disabled={disabled}
          placeholder={disabled ? "Add a document first" : "e.g. How much of the budget is left?"}
          className="min-w-0 flex-1 rounded-md border border-line bg-background px-3 py-2 text-sm outline-none focus:border-accent"
        />
        <button
          disabled={busy || disabled}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:text-black"
        >
          Ask
        </button>
      </form>
      <div className="mt-3 flex flex-wrap gap-2">
        {SUGGESTED.map((s) => (
          <button
            key={s}
            disabled={busy || disabled}
            onClick={() => submit(s)}
            className="rounded-md border border-line px-2 py-1 text-left text-xs text-muted hover:border-accent disabled:opacity-50"
          >
            {s}
          </button>
        ))}
      </div>

      {busy && <p className="mt-4 text-sm text-muted">Searching the documents…</p>}
      {error && <p className="mt-4 text-sm text-warn">{error}</p>}
      {answer && (
        <div className="mt-4 space-y-3">
          <p className="whitespace-pre-wrap text-sm leading-relaxed">{answer.answer}</p>
          {answer.citations.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-muted">Sources</h3>
              <ul className="mt-2 space-y-2">
                {answer.citations.map((c, i) => (
                  <li key={i} className="rounded-md bg-accent-soft px-3 py-2 text-xs">
                    <span className="font-medium">{c.source}</span>
                    <q className="mt-1 block text-muted">{c.cited_text.trim()}</q>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function NewUpload({ onCreated }: { onCreated: (id: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="rounded-xl border border-line bg-surface p-5">
      <h2 className="font-semibold">Upload your own loan documents</h2>
      <p className="mt-1 text-sm text-muted">
        Creates a private loan file only you can see, deleted after 24 hours. Up to 8 PDFs of 15 pages each. Use sample or
        made-up documents: don&apos;t upload real borrower information.
      </p>
      <button
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            onCreated((await api.createLoanFile("My loan file")).id);
          } catch (e) {
            setError(e instanceof ApiError ? e.message : "Couldn't create the loan file.");
          } finally {
            setBusy(false);
          }
        }}
        className="mt-4 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:text-black"
      >
        Start a loan file
      </button>
      {error && <p className="mt-3 text-sm text-warn">{error}</p>}
    </div>
  );
}

function Uploader({ loanFileId, count, onUploaded }: { loanFileId: string; count: number; onUploaded: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const upload = async (files: FileList) => {
    setBusy(true);
    let done = 0;
    for (const file of Array.from(files)) {
      setStatus(`Reading ${file.name}… (${done + 1} of ${files.length})`);
      try {
        await api.upload(loanFileId, file);
        done++;
        onUploaded();
      } catch (e) {
        setStatus(`${file.name}: ${e instanceof ApiError ? e.message : "upload failed"}`);
        setBusy(false);
        return;
      }
    }
    setStatus(`Added ${done} document${done === 1 ? "" : "s"}.`);
    setBusy(false);
  };

  return (
    <div className="rounded-xl border border-dashed border-line bg-surface p-5">
      <p className="text-sm text-muted">
        {count}/8 documents. Each PDF takes 10 to 20 seconds to read. Try the sample PDFs linked under the other tabs.
      </p>
      <input
        ref={input}
        type="file"
        accept="application/pdf"
        multiple
        className="hidden"
        onChange={(e) => e.target.files?.length && upload(e.target.files)}
      />
      <button
        disabled={busy || count >= 8}
        onClick={() => input.current?.click()}
        className="mt-3 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:text-black"
      >
        Add PDFs
      </button>
      {status && <p className="mt-3 text-sm">{status}</p>}
    </div>
  );
}
