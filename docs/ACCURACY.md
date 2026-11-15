# How accuracy is engineered and measured

## The principle: AI reads, code decides

| Step | Done by | Can it hallucinate? |
|---|---|---|
| Reading the invoice (transcribing fields) | Claude | Yes, so it is checked by the next step |
| Checking each value exists in the document | Code (`extract/evidence.py`) | No |
| Parsing amounts, dates, TRNs, currency | Code (`ingest/normalize.py`) | No: it either parses unambiguously or raises an error |
| Arithmetic (line totals, VAT, grand total) | Code (`rules/checks.py`, `Decimal`) | No |
| Compliance decisions | YAML rules + pure functions | No |
| All user-facing wording (EN/AR) | Fixed templates in `i18n/` and the rule packs | No |

The model never produces a number that the code does not independently find in the
document. It never makes a decision, and it never writes text the client reads.

## The guardrails, in order

1. **Schema-constrained output.** Claude must fill a fixed JSON schema (structured
   outputs). Every field is `{value, evidence}`, and `null` is the expected answer when
   something is not printed.
2. **Value-in-evidence.** The value must appear inside its own evidence quote.
3. **Evidence-in-document.** The quote, and the value itself, must be found in the PDF's
   text layer after normalisation:
   - NFKC folds Arabic presentation forms back to base letters.
   - Arabic-Indic digits become ASCII.
   - Diacritics and tatweel are removed, and alef/ya/ta-marbuta variants are unified.
   - Whitespace is collapsed.

   For Arabic documents, digit runs that the PDF extractor reversed into visual order are
   also accepted.
4. **Consensus.** In live mode, two independent passes must agree on every field. Line
   item counts must also match.
5. **Strict parsing.** Ambiguous amounts (`1.234,50`, `12 34`), impossible dates
   (`31/02/2026`) and unknown currencies become INVALID. They are never coerced.
6. **Abstention.** Any field that is unverified, disputed or invalid triggers GUARD-001 and
   🟡 *Needs review*. A missing-field rule never fires on an unverified value, so the tool
   never claims "TRN missing" when it simply could not read it.
7. **Photos and scans** (no text layer) are always 🟡. They cannot be machine-verified.

## What `famcheck eval` reports

- **Decision accuracy.** For each golden invoice: is the status, the exact set of rule IDs
  and the e-invoicing verdict as expected?
- **Auto-approved precision.** Of the values the tool used *without* a human (verified),
  the share that equal the ground truth. **This is the number that matters for trust.**
- **Coverage.** The share of ground-truth values that were verified, and therefore did
  not need a human.
- **Wrong values caught / missed.** A missed value is a wrong value that was auto-approved.
  The CI target is **0**.

### Today's numbers and what they mean

With the bundled replay cache (hand-written ground truth plus one deliberately corrupted
extraction), the results are **14/14 decisions, 363/363 auto-approved precision, 1 caught,
0 missed**.

These numbers prove two things:

- the rules engine produces exactly the expected decisions;
- the guardrail catches a misread value.

They **do not** yet measure Claude's reading accuracy. To measure it, run:

```bash
famcheck record fixtures/invoices   # needs ANTHROPIC_API_KEY; about 28 calls (14 invoices x 2 passes)
```

```bash
famcheck eval
```

Then add real (anonymised) FAM client invoices to the golden set. That is the accuracy
number to quote to clients.

## Known limits

- **Short values.** A quantity of "1" or a rate of "5%" is trivially found somewhere in
  most documents. Arithmetic cross-checks (qty × unit = net, Σ lines = subtotal,
  rate × base = VAT, subtotal + VAT = total) are what really protect these values.
- **Arabic token matching.** For RTL text the extractor can reorder words, so evidence is
  matched token by token. This is weaker than an exact phrase match. The value itself must
  still be present.
- **Scans and photos.** These need OCR (for example Tesseract with Arabic) before they can
  move from 🟡 to 🟢.
