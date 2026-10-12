# Synthetic sample cases

Three handcrafted cases exercise the whole pipeline deterministically.
Fixtures live in `cases/*.txt` (plain-text stand-ins for the PDFs — the
ingester treats `.txt` natively, no OCR needed); expected outcomes live in
`backend/tests/fixtures/expected_cases.json`.

| Case | Story | Expected outcome |
|------|-------|------------------|
| `case1_clean` | Consistent pack: deed + valuation + legal opinion, same owner (Ananya Deshpande), areas 4,000/4,002 sq ft (0.05% drift), fresh dates | `completed`, risk `low`, no unresolved flags |
| `case2_mismatch` | Deed says 4,000 sq ft, valuation says 5,000 sq ft (25% drift, limit 2%) | `needs_review`, `area_mismatch` (high), risk `high` |
| `case3_missing_expired` | Valuation + legal opinion dated 2019 (stale: >12 / >24 months) | expired flags (`stale_valuation`, `expired_doc:legal_opinion`) + missing-doc checks from the YAML checklist |

## Demo run

```bash
make test    # full suite incl. tests/test_e2e_synthetic.py (3 cases through the full graph)
```

The e2e test exercises ingest ▶ extract (mock LLM) ▶ crosscheck ▶ checklist
▶ report ▶ route on the real fixture files and asserts the deterministic
buckets above. Swap the mock provider for a real OpenRouter key and the same
fixtures run through live extraction.
