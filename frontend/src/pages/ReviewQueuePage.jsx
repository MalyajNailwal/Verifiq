import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";

export default function ReviewQueuePage() {
  const [tasks, setTasks] = useState(null);
  const [error, setError] = useState(null);
  const [notes, setNotes] = useState({});
  const [busyId, setBusyId] = useState(null);

  async function load() {
    try {
      setTasks(await api.listReviewTasks());
    } catch (err) {
      setError(String(err.message || err));
    }
  }
  useEffect(() => { load(); }, []);

  async function decide(task, decision) {
    setBusyId(task.id);
    setError(null);
    try {
      await api.resolveTask(task.id, {
        decision,
        reviewer_notes: notes[task.id] || null,
        decided_by: "web-reviewer",
      });
      await load();
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setBusyId(null);
    }
  }

  if (error) {
    return <p className="border-2 border-stamp text-stamp font-mono px-4 py-3">{error}</p>;
  }
  if (!tasks) return <p className="font-mono text-sm text-ink/50">Loading queue…</p>;

  return (
    <section>
      <div className="flex items-baseline justify-between">
        <h1 className="font-display font-black text-4xl">Review queue</h1>
        <span className="font-mono text-xs uppercase tracking-widest text-ink/50">
          {tasks.length} open task{tasks.length === 1 ? "" : "s"}
        </span>
      </div>
      <p className="mt-2 text-ink/60 max-w-2xl">
        Anything the machine was unsure about — low-confidence fields or high-severity
        flags — waits here for a qualified human decision.
      </p>

      <div className="mt-8 grid gap-4">
        {tasks.map((task) => (
          <div key={task.id} className="border-2 border-ink bg-white/70 p-5">
            <div className="flex justify-between items-start gap-4">
              <div>
                <p className="font-mono text-xs uppercase tracking-widest text-stamp">
                  {task.reason}
                </p>
                <Link
                  to={`/cases/${task.case_id}`}
                  className="font-display font-semibold text-xl hover:underline"
                >
                  case {task.case_id.slice(0, 8)} →
                </Link>
                {task.triggers?.low_confidence_fields?.length > 0 && (
                  <p className="mt-2 font-mono text-[11px] text-ink/60">
                    {task.triggers.low_confidence_fields.length} low-confidence field(s) need eyes
                  </p>
                )}
              </div>
              <span className="font-mono text-[11px] uppercase border-2 border-rule px-2 py-1">
                {task.status.replace("_", " ")}
              </span>
            </div>
            <textarea
              rows={2}
              placeholder="Reviewer notes…"
              value={notes[task.id] || ""}
              onChange={(e) => setNotes((n) => ({ ...n, [task.id]: e.target.value }))}
              className="mt-4 w-full border border-rule bg-paper px-3 py-2 text-sm focus:outline-none focus:border-ink"
            />
            <div className="mt-3 flex gap-3">
              <button
                disabled={busyId === task.id}
                onClick={() => decide(task, "approved")}
                className="bg-verify text-white px-5 py-2 font-mono text-xs uppercase tracking-widest hover:bg-verify/85 disabled:opacity-50"
              >
                Approve
              </button>
              <button
                disabled={busyId === task.id}
                onClick={() => decide(task, "rejected")}
                className="border-2 border-stamp text-stamp px-5 py-2 font-mono text-xs uppercase tracking-widest hover:bg-stamp/10 disabled:opacity-50"
              >
                Reject
              </button>
            </div>
          </div>
        ))}
        {!tasks.length && (
          <p className="border-2 border-rule p-6 font-mono text-sm text-ink/50">
            Queue is empty — no cases awaiting review.
          </p>
        )}
      </div>
    </section>
  );
}
