# Demo guide: presenting FAM Invoice Checker to the founder

There are two ways to show the product:

1. **Send the recorded video** (`demo.mp4`, about 3 minutes, English subtitles). This works
   well as a first message on LinkedIn, WhatsApp or email.
2. **Give a live demo** of 7–10 minutes, following the script below. The demo needs no
   internet connection and no API key.

## The video's storyline

| Time (approx.) | Scene | Message |
|---|---|---|
| 0:00 | Title | "FAM Invoice Checker: built for FAM Advisory" |
| 0:08 | The problem | 500+ VAT clients; one bad invoice means lost input VAT; e-invoicing in 2027 |
| 0:20 | Upload screen | Any PDF or photo, in English or Arabic |
| 0:30 | Dashboard | 4 valid / 2 review / 8 problems; **AED 1,998 VAT at risk**; **21% e-invoicing ready** |
| 0:55 | Wrong VAT invoice | Code recomputes the VAT; every finding cites its legal basis |
| 1:10 | Arabic invoice | Native Arabic; each value is shown with the exact text it came from |
| 1:25 | AI misread | The guardrail catches it, because the tool never guesses |
| 1:40 | Photo | Never auto-approved |
| 1:45 | Arabic UI | One click switches to full right-to-left |
| 1:55 | Client report | English and Arabic, ready to send |
| 2:10 | Exports | Excel for the team; Zoho CSV with valid invoices only |
| 2:15 | Rules | The tax team can sign off rules without touching code |
| 2:22 | Terminal | 14/14 decisions correct; 0 wrong values auto-approved |
| 2:32 | Value + pilot | Team / Clients / Growth, then a 2-week pilot |

## Live demo script (what to say)

**Opening (30 s).** "I looked at FAM's website. You serve 500+ VAT clients, and every
return starts with someone checking invoices by hand, in English and Arabic. From 2027,
e-invoicing becomes mandatory and your site doesn't have an offer for it yet. So I built
something for both problems."

**Run the demo (1 min).** Run `famcheck serve`, then click **Run demo on 14 sample
invoices**. Point at the four numbers, then say: "AED 1,998 of VAT at risk, found
*before* filing. And only 21% of these invoices are ready for e-invoicing. That is the
conversation you'd have with every client."

**Trust (2 min). This is the part that wins accountants over.**
- Open the *Pure Aqua* invoice: "The AI only reads. The maths is plain code. Here is the
  rule and its legal basis."
- Open the Arabic invoice: "Every value shows the exact words it came from in the
  document."
- Open *Golden Fork*: "Here I made the AI misread one digit on purpose. The tool couldn't
  find that number in the document, so it threw the value away and asked a human. It
  never guesses."

**Arabic and the client report (1 min).** Click the language toggle, then open
**Client report**. Say: "This goes straight to the client, in English or Arabic."

**For the team (30 s).** Show the **Excel** export and the **Zoho CSV**. Say: "Only valid
invoices go to Zoho. Your team already uses Zoho."

**Close (30 s).** "I'd like to run a 2-week pilot: your tax team signs off the rules, we
run it on 50 anonymised real invoices, and I measure the accuracy in front of you."

## Questions you will likely get

| Question | Answer |
|---|---|
| "Is it accurate?" | The AI only reads, and every value is checked against the document. On the test set: 14/14 decisions correct, 0 wrong values let through. The pilot measures accuracy on real invoices. |
| "What about client confidentiality?" | Documents go only to the Anthropic API during reading. Nothing is stored by the app. It can run on FAM's own machine. |
| "Does it replace my team?" | No. It removes the re-keying and checking, so the team works on exceptions and advice. |
| "What does it cost to run?" | An estimated 10–20 US cents per invoice in API costs with two reading passes (to be measured in the pilot). Re-runs are free because results are cached. |
| "Can it do X?" (other VAT rules, corporate tax) | Yes. Rules are plain YAML files, so adding a rule is a small change. |

## Re-recording the video

```bash
scripts/make_demo_video.sh demo_out "Your Name"
```

This writes `demo_out/demo.mp4` and `demo_out/demo.srt`. The scenes and captions are in
`scripts/record_demo.js`.
