import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../api.js";

const STATUS_COLORS = {
  uploaded: "bg-ink/10 text-ink",
  processing: "bg-amber-400/30 text-ink",
  needs_review: "bg-amber-400/60 text-ink",
  completed: "bg-verify/15 text-verify",
  rejected: "bg-stamp/15 text-stamp",
};

const SEV_COLORS = {
  high: "text-stamp border-stamp",
  medium: "text-amber-400 border-amber-400 text-ink",
  low: "text-ink/60 border-rule",
};

function confColor(c) {
  if (c >= 0.9) return "bg-verify/15 text-verify";
  if (c >= 0.75) return "bg-amber-400/25 text-ink";
  return "bg-stamp/15 text-stamp";
}

function FieldsTable({ fields }) {
  if (!fields.length) return <p className="text-ink/50 font-mono text-sm">Extraction in progress…</p>;
  return (
    <table className="w-full text-sm border-2 border-ink bg-white/70">
      <thead>
        <tr className="font-mono text-[11px] uppercase tracking-widest text-left border-b-2 border-ink">
          <th className="px-3 py-2">Field</th>
          <th className="px-3 py-2">Value</th>
          <th className="px-3 py-2 w-24">Confidence</th>
          <th className="px-3 py-2 w-16">Page</th>
        </tr>
      </thead>
      <tbody>
        {fields.map((f) => (
          <tr key={f.id} className="field-row relative border-b border-rule/60 align-top group">
            <td className="px-3 py-2 font-mono text-xs">{f.field_name}</td>
            <td className="px-3 py-2 relative">
              {f.value == null ? (
                <span className="text-ink/40 font-mono text-xs">null ({f.extraction_reason})</span>
              ) : (
                renderValue(f.value)
              )}
              {f.source_snippet && (
                <span className="snippet hidden absolute left-2 top-full mt-1 z-10 w-96 border-2 border-ink bg-paper p-3 font-mono text-[11px] shadow-lg">
                  “{f.source_snippet}”
                </span>
              )}
            </td>
            <td className={`px-3 py-2 font-mono text-xs ${confColor(f.confidence)}`}>
              {f.confidence.toFixed(2)}
            </td>
            <td className="px-3 py-2 font-mono text-xs">{f.source_page ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function renderValue(raw) {
  try {
    const v = JSON.parse(raw);
    if (Array.isArray(v)) return v.join("; ");
    if (typeof v === "object" && v !== null) {
      return Object.entries(v).map(([k, x]) => `${k}: ${x}`).join(" · ");
    }
    return String(v);
  } catch {
    return String(raw);
  }
}

export default function CasePage() {
  const { caseId } = useParams();
  const [data, setData] = useState(null);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const c = await api.getCase(caseId);
        if (alive) setData(c);
        if (c.status !== "processing") {
          const r = await api.getReport(caseId).catch(() => null);
          if (alive) setReport(r);
        }
      } catch (err) {
        if (alive) setError(String(err.message || err));
      }
    }
    load();
    const t = setInterval(load, 4000);
    return () => { alive = false; clearInterval(t); };
  }, [caseId]);

  if (error) {
    return <p className="border-2 border-stamp text-stamp font-mono px-4 py-3">{error}</p>;
  }
  if (!data) return <p className="font-mono text-sm text-ink/50">Loading case…</p>;

  return (
    <section className="relative">
      <Link to="/" className="font-mono text-xs uppercase tracking-widest hover:underline">← new case</Link>
      <div className="flex items-start justify-between gap-6 mt-3">
        <div>
          <h1 className="font-display font-black text-4xl">{data.asset_name}</h1>
          <p className="font-mono text-xs mt-2 text-ink/60">
            {data.asset_type} · {data.jurisdiction || "jurisdiction n/a"} · case {caseId.slice(0, 8)}
          </p>
        </div>
        <span className={`px-4 py-2 font-mono text-xs uppercase tracking-widest border-2 border-ink ${STATUS_COLORS[data.status] || ""}`}>
          {data.status.replace("_", " ")}
        </span>
      </div>

      {data.status === "processing" && (
        <div className="mt-6 border-2 border-ink/30 p-4 font-mono text-xs animate-pulse">
          pipeline running — ingesting, extracting, cross-checking… (auto-refreshing)
        </div>
      )}

      {report && (
        <div className="mt-8 border-2 border-ink bg-white/70 p-6 relative">
          <div className="absolute -top-4 right-6 stamp bg-paper text-sm">
            {report.risk_rating} risk
          </div>
          <h2 className="font-display font-semibold text-2xl">Verification report</h2>
          <p className="mt-3 max-w-3xl leading-relaxed">{report.summary}</p>
          {report.checklist && (
            <ul className="mt-4 grid gap-1 font-mono text-xs">
              {report.checklist.map((c) => (
                <li key={c.doc_type}>
                  <span className={c.present ? "text-verify" : "text-stamp"}>
                    {c.present ? "✔" : "✘"}
                  </span>{" "}
                  {c.doc_type} — {c.status}
                  {c.required ? " (required)" : " (optional)"}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-4 font-mono text-[11px] text-ink/50">
            report hash: <span className="select-all">{report.report_hash}</span>
          </p>
          <a
            href={api.reportDownloadUrl(caseId)}
            target="_blank" rel="noreferrer"
            className="inline-block mt-4 bg-ink text-paper px-5 py-2 font-mono text-xs uppercase tracking-widest hover:bg-ink/85"
          >
            Download report
          </a>
        </div>
      )}

      <h2 className="font-display font-semibold text-2xl mt-10">Extracted fields</h2>
      <div className="mt-3">
        <FieldsTable fields={data.fields || []} />
      </div>

      <h2 className="font-display font-semibold text-2xl mt-10">Verification flags</h2>
      <div className="mt-3 grid gap-2">
        {(data.flags || []).map((f) => (
          <div key={f.id} className={`border-2 ${SEV_COLORS[f.severity] || SEV_COLORS.low} p-3 bg-white/60`}>
            <div className="flex justify-between font-mono text-[11px] uppercase">
              <span>{f.flag_type}</span>
              <span>{f.severity}{f.resolved ? " · resolved" : ""}</span>
            </div>
            <p className="mt-1 text-sm">{f.description}</p>
          </div>
        ))}
        {!(data.flags || []).length && (
          <p className="text-ink/50 font-mono text-sm">No flags — documents are consistent.</p>
        )}
      </div>

      {(data.flags || []).some((f) => !f.resolved) && (
        <p className="mt-6 font-mono text-xs text-ink/60">
          Flagged items require human review — see the{" "}
          <a href="/review" className="underline">review queue</a>.
        </p>
      )}
    </section>
  );
}
