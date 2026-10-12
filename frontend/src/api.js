const base = "/api";

async function json(res) {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  createCase: (payload) =>
    fetch(`${base}/cases`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(json),

  uploadDocuments: (caseId, files, docTypes) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    docTypes.forEach((t) => fd.append("doc_types", t));
    return fetch(`${base}/cases/${caseId}/documents`, { method: "POST", body: fd }).then(json);
  },

  runCase: (caseId) =>
    fetch(`${base}/cases/${caseId}/run`, { method: "POST" }).then(json),

  getCase: (caseId) => fetch(`${base}/cases/${caseId}`).then(json),

  getReport: (caseId) => fetch(`${base}/cases/${caseId}/report`).then(json),

  reportDownloadUrl: (caseId) => `${base}/cases/${caseId}/report/download`,

  listReviewTasks: () => fetch(`${base}/review-tasks`).then(json),

  resolveTask: (taskId, payload) =>
    fetch(`${base}/review-tasks/${taskId}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(json),
};
