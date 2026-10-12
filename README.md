# Verifiq — RWA DiligenceAI

**Agentic document-verification for real-world-asset (RWA) tokenization.**

> ⚠️ **Disclaimer — read first.** Verifiq verifies documents and flags risk **only**.
> It **never** gives investment advice (no buy/sell/invest recommendations). Every
> generated report carries a mandatory disclaimer and **must** be signed off by a
> qualified human reviewer before any use.

[![Python](https://img.shields.io/badge/python-3.11+-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green)](https://fastapi.tiangolo.com/)
[![Tests](https://img.shields.io/badge/tests-97%20passing-brightgreen)](backend/tests)
[![Lint](https://img.shields.io/badge/ruff-clean-success)](https://docs.astral.sh/ruff/)

---

## 1. The problem

Before land or real estate is tokenized on-chain, its documents — title deed, valuation
report, legal opinion, SPV/ownership papers — must be verified. Today this is manual,
slow, and error-prone:

- Owner names differ across documents (spelling variants, initials).
- Areas are quoted in inconsistent units (sq ft vs sq m, acres, guntha...).
- Valuations are stale, liens/encumbrances are buried in boilerplate.
- Required documents are simply missing — and nobody notices until late.

**Verifiq ingests the document pack, extracts key facts with confidence scores and
page-level source references, cross-checks for inconsistencies, flags missing/expired
documents, and produces an investor-ready risk report — with a human-review step for
anything the machine is unsure about.**

## 2. Use cases

| # | Use case | Who benefits | How Verifiq helps |
|---|----------|--------------|-------------------|
| 1 | **Pre-tokenization due diligence** | RWA tokenization platforms | Automated first-pass on every asset's document pack before an offering goes live |
| 2 | **Missing-document detection** | Compliance teams | Checklist per asset type flags absent title deeds / valuations / legal opinions immediately |
| 3 | **Cross-document consistency checks** | Legal & risk analysts | Deterministic rules catch owner-name mismatches, area drift beyond 2% after unit normalization, parcel/address conflicts, stale valuations (>12 months), unresolved liens |
| 4 | **Human-in-the-loop review** | Reviewers / underwriters | Anything low-confidence or high-severity lands in a review queue; reviewers edit fields and approve/reject with notes |
| 5 | **Audit trail & report provenance** | Investors, auditors | Every extracted field carries confidence + source (doc + page); every report is hashed (SHA-256), optionally anchored on Polygon testnet (later phase) |
| 6 | **Multi-jurisdiction scaling** | Platforms operating across states | Checklist + rules are config-driven (YAML), not hardcoded |

## 3. Design guarantees (hard constraints)

1. **Risk flagging only** — no investment advice anywhere in the product; disclaimer on every report.
2. **Every extracted field** carries a **confidence score** and a **source reference** (document + page).
3. **Human review gate**: fields below the confidence threshold (default `0.75`) or any **High**-severity flag ⇒ case goes to `needs_review`, never straight to `completed`.
4. **All LLM output is schema-validated** (Pydantic v2) with automatic retry on invalid output.
5. **Never invent data**: a missing field is `null` with reason `"not_found"` — never guessed.
6. **Provider-agnostic LLM**: one `LLMClient` interface; **OpenRouter by default** (one key, any model), direct Claude/OpenAI/Gemini adapters included.

## 4. Architecture (current status: Phase 1 complete)

```
                         ┌──────────────────────────────────────┐
 Upload documents ──────▶ │  FastAPI  /cases  /review-tasks      │
                         └──────────────┬───────────────────────┘
                                        ▼
   PostgreSQL (cases, documents, pages, fields, flags, reports, review_tasks, llm_logs)
                                        ▲
                         ┌──────────────┴───────────────────────┐
                         │  LangGraph pipeline (Phase 2-4)      │
                         │  Ingest ▶ Extract ▶ CrossCheck ▶     │
                         │  Checklist ▶ Report ▶ Router         │
                         └──────────────┬───────────────────────┘
                                        ▼
                         ┌──────────────────────────────────────┐
                         │  LLMClient (swappable)               │
                         │  openrouter │ claude │ openai │      │
                         │  gemini │ mock                       │
                         └──────────────────────────────────────┘
```

### Agents (planned → delivered by phase)
| Phase | Component | Status |
|-------|-----------|--------|
| 1 | Scaffold, DB + migrations, config, LLMClient (OpenRouter default) | ✅ **done** |
| 2 | IngestNode (text PDFs via pdfplumber, `.txt` passthrough, vision flags; PaddleOCR hook), ExtractionAgent (versioned prompts + few-shot, schema-validated, persisted with confidence + source) | ✅ **done** |
| 3 | CrossCheckAgent + ChecklistAgent (deterministic rules, YAML-driven) | ✅ **done** |
| 4 | ReportAgent (rule-based score + LLM wording) + RouterNode + LangGraph wiring + full API + React frontend (upload, case page, review queue) | ✅ **done** |
| 5 | React frontend (upload, case page, review queue) | ✅ **done** (Vite + Tailwind, "verification registry" aesthetic) |
| 6 | Polygon Amoy hash anchoring (optional): report SHA-256 written as tx calldata on Amoy testnet, `POST /cases/{id}/report/anchor`, idempotent, `web3` optional extra | ✅ **done** |
| 7 | Demo script + end-to-end tests with 3 synthetic cases | ✅ **done** (e2e runs the 3 samples through the full graph) |

## 5. Quickstart

### Prereqs
Python 3.11+, Docker (for Postgres), an [OpenRouter API key](https://openrouter.ai/keys).

```bash
# 1. Configure
cp .env.example .env          # then set OPENROUTER_API_KEY=sk-or-...

# 2. Install
make install                  # venv + backend deps (incl. dev)

# 3. Run Postgres + API
make db-up                    # docker compose up -d db
make migrate                  # alembic upgrade head
make run                      # http://localhost:8000

# No Docker? Use SQLite instead of step 3's db:
#   DATABASE_URL=sqlite:///./dev.db make migrate && DATABASE_URL=sqlite:///./dev.db make run
```

Check: `curl localhost:8000/health` →
`{"status":"ok","database":"ok","llm_provider":"openrouter",...}`

### Quality gates
```bash
make test    # pytest + coverage
make lint    # ruff check + format check
make format  # auto-fix
```

## 6. LLM configuration (OpenRouter)

**Recommended:** OpenRouter — one API key, any model. Set in `.env`:

```env
LLM_PROVIDER=openrouter
LLM_MODEL=anthropic/claude-sonnet-4     # or openai/gpt-4o-mini, google/gemini-2.0-flash-001, ...
OPENROUTER_API_KEY=sk-or-v1-...
```

- Model ids follow OpenRouter's `vendor/model` convention — see [openrouter.ai/models](https://openrouter.ai/models).
- The adapter calls the OpenAI-compatible REST API directly via `httpx` (no extra SDK).
- Alternative direct providers still work: `LLM_PROVIDER=claude|openai|gemini` with the
  matching `*_API_KEY`. For tests/CI with no keys: `LLM_PROVIDER=mock` (deterministic).
- Every LLM call is logged (provider, model, prompt version, tokens, latency) in `llm_call_logs`.

## 7. Project layout

```
backend/
├── app/
│   ├── api/            # FastAPI routers (health, cases, documents, reports, reviews)
│   ├── core/           # config (typed settings), db, logging
│   │   └── llm/        # LLMClient ABC + openrouter/claude/openai/gemini/mock adapters
│   ├── models/         # SQLAlchemy 2.0 ORM (Case, Document, ExtractedField, Flag, ...)
│   ├── schemas/        # Pydantic v2 API + LLM structured-output schemas
│   ├── prompts/        # versioned prompt templates (extraction_v1, report_summary_v1)
│   └── services/       # ingest, extraction, crosscheck, checklist, report, router, graph
│       └── checklists.yaml  # per-asset-type required-docs + validity windows
├── alembic/            # migrations (0001 initial schema)
├── tests/              # 97 tests: unit + API + e2e synthetic cases + anchoring
├── samples/cases/      # 3 synthetic case packs (clean / mismatch / stale) for the demo
├── Dockerfile
└── pyproject.toml
docker-compose.yml      # Postgres 16 + API
frontend/               # React (Vite + Tailwind): new case, case detail, review queue
Makefile  .env.example  .pre-commit-config.yaml
```

## 8. Database entities

`Case` (asset + status: uploaded → processing → needs_review/completed/rejected) →
`Document` (doc_type, sha256, OCR status) → `DocumentPage` (per-page text) →
`ExtractedField` (value, confidence, source page/snippet). A case collects `Flag`
(severity, type, rule), one `Report` (rating, summary, checklist, SHA-256 hash) and
`ReviewTask` entries for the human queue. `LLMCallLog` audits every model call.

## 9. API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness + DB + provider status |
| POST/GET | `/cases` | Create a case; list all cases |
| GET | `/cases/{id}` | Case detail (documents, fields, flags) |
| POST | `/cases/{id}/documents` | Upload a document (stored content-addressed, SHA-256 dedupe) |
| POST | `/cases/{id}/run` | Run the full pipeline (ingest▶extract▶crosscheck▶checklist▶report▶route) |
| GET | `/cases/{id}/report` | Verification report (deterministic rating + hash) |
| POST | `/cases/{id}/report/anchor` | Anchor report hash on Polygon Amoy (optional, `make install-chain`) |
| GET | `/review-tasks` | Human review queue |
| POST | `/review-tasks/{id}/decide` | Approve/reject with notes |

## 10. Contributing

```bash
pip install pre-commit && pre-commit install   # ruff + hooks on commit, pytest on push
make revision m="add xyz column"               # new Alembic migration
```

License: TBA. Maintained by [@MalyajNailwal](https://github.com/MalyajNailwal).
