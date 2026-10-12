import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import "./styles.css";
import NewCasePage from "./pages/NewCasePage.jsx";
import CasePage from "./pages/CasePage.jsx";
import ReviewQueuePage from "./pages/ReviewQueuePage.jsx";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <div className="min-h-screen bg-paper text-ink font-sans">
        <header className="border-b-2 border-ink bg-paper sticky top-0 z-20">
          <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
            <a href="/" className="flex items-baseline gap-3 no-underline text-ink">
              <span className="font-display font-black text-2xl tracking-tight">Verifiq</span>
              <span className="font-mono text-[10px] uppercase tracking-[0.25em] text-ink/60">
                RWA document verification
              </span>
            </a>
            <nav className="flex gap-6 font-mono text-xs uppercase tracking-widest">
              <a className="hover:underline underline-offset-4" href="/">New case</a>
              <a className="hover:underline underline-offset-4" href="/review">Review queue</a>
            </nav>
          </div>
        </header>
        <main className="max-w-6xl mx-auto px-6 py-10">
          <Routes>
            <Route path="/" element={<NewCasePage />} />
            <Route path="/cases/:caseId" element={<CasePage />} />
            <Route path="/review" element={<ReviewQueuePage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
        <footer className="max-w-6xl mx-auto px-6 pb-10 pt-4 border-t border-rule mt-16">
          <p className="font-mono text-[11px] leading-relaxed text-ink/50">
            DISCLAIMER — Verifiq verifies documents and flags risk only. It is NOT
            investment advice and must not be relied upon to buy, sell, or invest in any
            asset. A qualified human reviewer must validate all flagged items.
          </p>
        </footer>
      </div>
    </BrowserRouter>
  </React.StrictMode>
);
