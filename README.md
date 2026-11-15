# FAM Invoice Checker

**UAE VAT tax-invoice compliance and e-invoicing readiness, in English and Arabic.**

A proof of concept built for FAM Advisory. Upload a client's batch of supplier
invoices (PDF or photo; English, Arabic or bilingual). For each invoice the tool:

1. **Reads it.** Claude copies every field verbatim, together with the exact text it came from.
2. **Checks the reading.** Each value must be found in the document's own text. Values that are not found are thrown away, never guessed.
3. **Applies the rules.** It checks UAE tax-invoice requirements, recomputes the VAT arithmetic, checks TRN format, looks for duplicates, confirms the invoice is addressed to the client, and checks e-invoicing data gaps.
4. **Labels the invoice:**
   - 🟢 **Valid**
   - 🟡 **Needs review**: something could not be verified, so a person must look
   - 🔴 **Problem found**: the client's input VAT is at risk. The finding states the reason and the legal basis.
5. **Writes the outputs:**
   - an Excel workbook for the team
   - a Zoho Books CSV containing valid invoices only
   - a JSON audit trail
   - a client report in English and Arabic: *"21% of your invoices are e-invoicing ready. Here are the gaps."*

> E-invoicing becomes mandatory for UAE businesses with revenue of AED 50M or more on
> **1 January 2027**. All other businesses must appoint an Accredited Service Provider by
> **31 March 2027** and go live on **1 July 2027**. *(Check these dates with the MoF/FTA before client use.)*

---

## Quick start (about 2 minutes, no API key needed)

```bash
git clone <this repo> && cd fam-tax-copilot
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Run the demo on the 14 bundled sample invoices. It works offline:

```bash
famcheck demo
```

Start the web app, then open http://127.0.0.1:8000 and click **"Run demo on 14 sample invoices"**:

```bash
famcheck serve
```

Other commands:

```bash
famcheck eval            # golden-set accuracy report
```

```bash
famcheck rules           # every rule with its legal basis
```

```bash
pytest                   # 56 automated tests
```

### Checking real invoices (needs a Claude API key)

```bash
cp .env.example .env     # then put your key in ANTHROPIC_API_KEY=...
```

```bash
famcheck review path/to/invoices --client-name "Client LLC" --client-trn 100xxxxxxxxxxxx --open
```

Each new invoice is read once by Claude, by default **twice** so the two readings can be cross-checked. The result is cached by file hash, so running the same file again is free and gives identical output.

To replace the demo's hand-written cache with real Claude extractions and measure Claude's accuracy, run:

```bash
famcheck record fixtures/invoices && famcheck eval
```

---

## Why the results can be trusted

| Guardrail | What it prevents |
|---|---|
| **The model only copies.** It never calculates, judges or translates. Output is constrained to a JSON schema. | A "helpful" AI filling in a VAT amount that is not on the invoice |
| **Evidence check.** Every value must sit inside a quote, and that quote must be found in the PDF's own text layer. Arabic presentation forms and reversed digit runs are normalised before matching. | Hallucinated or misread values: the value is discarded and the invoice goes to a person |
| **Consensus.** Two independent passes must agree on every field. | Unstable readings |
| **Deterministic rules.** All arithmetic uses `Decimal`. Each rule is a YAML entry with an ID, a severity, a citation and an Arabic message. | Inconsistent judgement; rules nobody can audit |
| **Abstain, don't guess.** Unverifiable values, photos and scans, failed extractions and API errors all give 🟡 *Needs review*. | False green ticks |
| **Only valid invoices are exported to Zoho.** | Bad data reaching the books |
| **Golden set + CI.** `famcheck eval` fails if any decision changes or any wrong value is auto-approved. | Silent regressions |

Current golden-set result: **14/14 decisions correct, 0 wrong values auto-approved, 1 simulated AI misread caught.**
See [docs/ACCURACY.md](docs/ACCURACY.md) for what that number does and does not prove.

---

## The 14 sample invoices (fictitious client: *Al Noor Restaurants LLC*)

| File | Planted issue | Expected |
|---|---|---|
| inv01_en_valid | none | 🟢 |
| inv02_ar_valid | Arabic; supplier TRN printed in Arabic-Indic digits | 🟢 |
| inv03_bi_valid | Bilingual, above AED 10k, full invoice requirements met | 🟢 |
| inv04_en_vat_wrong | VAT 125.00 instead of 120.00 | 🔴 MATH-003 |
| inv05_en_no_tax_title | Titled "INVOICE" | 🔴 VAT-001 |
| inv06_en_bad_trn | 14-digit supplier TRN | 🔴 VAT-005 |
| inv07_ar_missing_customer_trn | Arabic, above AED 10k, no customer TRN | 🔴 VAT-013 |
| inv08_en_usd_no_aed | USD invoice without VAT in AED | 🔴 VAT-016 |
| inv09_en_duplicate | Same supplier TRN and invoice number as inv01 | 🔴 GUARD-004 |
| inv10_en_simplified | Valid simplified invoice, but no buyer data for e-invoicing | 🟢 + e-invoice gaps |
| inv11_en_wrong_customer | Addressed to another legal entity | 🔴 VAT-015 |
| inv12_img_receipt | Phone photo, so it cannot be machine-verified | 🟡 GUARD-002 |
| inv13_en_wrong_rate | 15% VAT | 🔴 VAT-010 |
| inv14_en_misread_guardrail | **Simulated AI misread** of the TRN | 🟡 GUARD-001 (caught) |

All companies and TRNs are made up. To regenerate the samples, see `scripts/make_fixtures.py`.

---

## Architecture

```
PDF / photo ─► ingest (text layer, SHA-256, language)
            ─► extract (Claude: verbatim values + evidence; or replay cache)   ← the only AI step
            ─► evidence + consensus check (discard anything unverifiable)
            ─► normalise (Decimal amounts, ISO dates/currency, TRN digits; EN + AR)
            ─► rules engine (YAML packs: VAT, arithmetic, guardrails, e-invoicing)
            ─► status + batch checks (duplicates) ─► reports (XLSX, CSV, JSON, HTML EN/AR)
```

The CLI (`famcheck`) and the web app (`famcheck serve`) run the **same** pipeline.

```
src/famcheck/
├── core/        models.py (schemas), build.py (typed invoice), pipeline.py (orchestration)
├── ingest/      loader.py (PDF text layer, hashing), normalize.py (EN/AR numbers, dates, TRN, currency)
├── extract/     claude.py (the only LLM call), evidence.py (guardrails), replay.py (cache)
├── rules/       packs/*.yaml (rules as data), checks.py (pure functions), engine.py
├── report/      writers.py (Excel, Zoho CSV, JSON, client HTML), templates/
├── i18n/        en.json, ar.json, fields.json (all user-facing text; the model writes none)
├── web/         FastAPI app, templates, CSS (RTL-aware, dark mode, mobile)
├── evaluate.py  golden-set scoring
└── cli.py       famcheck demo | review | record | eval | rules | serve
fixtures/        invoices/ (14 samples), golden/ (expected results + ground truth), replay/ (cache)
docs/            PITCH.md, ACCURACY.md, RULES_SIGNOFF.md
tests/           56 tests (normalisation, evidence, rules, golden set, web, CLI, extractor)
```

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | – | Needed only to read new invoices |
| `FAMCHECK_MODEL` | `claude-opus-5-5` | Extraction model |
| `FAMCHECK_MODE` | `auto` | `auto`: cache first, then live. `replay`: cache only. `live`: always call Claude. `record`: call Claude and save the result |
| `FAMCHECK_PASSES` | `2` | Independent extraction passes per invoice (consensus) |

## Status and limits (honest)

- **Proof of concept.** Rule citations are drafted and **must be signed off by FAM's tax team** ([docs/RULES_SIGNOFF.md](docs/RULES_SIGNOFF.md)). The e-invoicing pack is *indicative* until it is mapped to the official PINT AE data dictionary.
- The demo cache is hand-written ground truth. Claude's real accuracy is measured once `famcheck record` has been run with a key.
- Very short values, such as a quantity of "1", are weakly evidenced by text matching alone. Arithmetic cross-checks (qty × price = net) cover them.
- Scanned PDFs and photos are never auto-approved. Adding OCR would let them be verified.
- Client documents are sent to the Anthropic API only in live mode. Nothing is stored server-side by the web app beyond its in-memory session.
