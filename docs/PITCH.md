# FAM Invoice Checker: one-page pitch

**For:** the founder and core team of FAM Advisory
**From:** an AI and Forward-Deployed Engineer

## The problem, in FAM's own numbers

- FAM states that it has helped **500+ businesses** with VAT registration, filing and
  compliance. Every VAT return starts with someone checking a pile of supplier invoices by
  hand, often a mix of English and Arabic PDFs and WhatsApp photos.
- One invalid tax invoice (wrong title, missing TRN, wrong VAT, addressed to the wrong
  entity) means **input VAT the client cannot recover**. It is also the first thing an FTA
  audit looks at.
- **E-invoicing deadlines arrive in 2027** (1 Jan for revenue of AED 50M or more; 1 Jul for
  everyone else). Every FAM client will ask *"are we ready?"*, and famadvisory.ae has no
  e-invoicing offer yet.

## What the tool does

You drop in a client's invoices. Within minutes you get:

- 🟢 / 🟡 / 🔴 per invoice, with the reason and the legal basis, in **English and Arabic**
- **Input VAT at risk** in AED. In the demo, 14 invoices show AED 1,998 at risk.
- An **e-invoicing readiness %** and the most common data gaps
- An Excel workbook for the team, a **Zoho Books** CSV (FAM is a Zoho partner) containing
  valid invoices only, and a branded client report

## Why it can be trusted

The AI only *reads*. Every value must be found in the document, or it is discarded and a
person checks it. All maths and every decision are done by auditable rules that the tax
team can edit. On the golden set: **14/14 correct decisions; a simulated AI misread was
caught; 0 wrong values auto-approved.**

## Value

| For | Value |
|---|---|
| **Team** | Pre-return invoice review drops from hours to minutes per client. Juniors handle exceptions instead of re-keying. |
| **Clients** | VAT leakage is caught *before* filing. Clear Arabic and English reports. |
| **Founder** | A ready-made **e-invoicing readiness assessment**: a lead magnet for the Google Ads / WhatsApp funnel and a door-opener to paid remediation and Accredited Service Provider advisory work before the 2027 deadlines. |

## Proposed next steps (2–3 weeks)

1. FAM's tax team signs off the rule citations (an afternoon's work).
2. Run it on 50 anonymised real invoices and publish the measured accuracy.
3. Add OCR for photos and scans, connect Zoho Books via its API, and add a WhatsApp intake.
4. Launch "Free E-Invoicing Readiness Check" as a landing page on famadvisory.ae.
