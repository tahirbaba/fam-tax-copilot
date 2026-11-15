# Rule sign-off sheet (for FAM Advisory's tax team)

Every rule lives in `src/famcheck/rules/packs/*.yaml`. Each rule has:

- an ID
- a severity (`error`, `warning` or `info`)
- an applicability condition
- English and Arabic text
- a **citation**

The citations were **drafted by the tool author** and must be confirmed before any
client-facing use. A reviewer only needs to edit the YAML file; no code changes are
needed. After review, fill in `reviewed_by` and `reviewed_on` in the pack header. The
web app's *Rule packs* page and the Excel *Summary* sheet both show this status.

To list every rule with its citation:

```bash
famcheck rules
```

Add `--lang ar` for Arabic.

## Points that most need expert confirmation

| Rule | Assumption to confirm |
|---|---|
| VAT-001 … VAT-009 | Particulars of a tax invoice: VAT Executive Regulation (Cabinet Decision 52/2017, as amended), Art. 59(1) |
| VAT-011 … VAT-013 | A simplified tax invoice is acceptable only up to AED 10,000 when the recipient is registered (Art. 59(2)). The tool assumes the client (the recipient) is always VAT-registered. |
| VAT-015 | The client can only recover input VAT on invoices issued to its own TRN |
| VAT-016 | Foreign-currency invoices must show the VAT payable in AED |
| VAT-010 | Valid rates are 5% and 0%. Exempt and out-of-scope supplies carry no VAT line. |
| VAT-019 | Info only: UAE TRNs normally begin with "100" |
| EINV-* | Indicative. Map each one to the official MoF/FTA e-invoicing (PINT AE) data dictionary and the mandatory field list. |
| Deadlines | 1 Jan 2027 (revenue ≥ AED 50M); ASP appointment by 31 Mar 2027 and go-live 1 Jul 2027 (others). Confirm on mof.gov.ae. |

## Adding a rule

1. Add an entry to a pack. `check` must be one of the functions in `rules/checks.py`.
2. Add a sample invoice that triggers it (`scripts/make_fixtures.py`).
3. Run `pytest` and `famcheck eval`. CI keeps the golden set passing.
