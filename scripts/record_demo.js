// Records the guided product demo video (1280x720) with burned-in English captions,
// a visible cursor and highlight boxes, and writes a matching .srt subtitle file.
//
// Usage:
//   famcheck serve --port 8765 &                       # start the app first
//   node scripts/record_demo.js [outDir] [presenter]   # needs the `playwright` npm package
//   -> outDir/demo.webm + outDir/demo.srt   (scripts/make_demo_video.sh converts to MP4)
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = process.env.DEMO_URL || "http://127.0.0.1:8765";
const OUT = path.resolve(process.argv[2] || "demo_out");
const PRESENTER = process.argv[3] || process.env.DEMO_PRESENTER || "";
const W = 1280, H = 720;

const NAVY = "#0b3d5c", GOLD = "#b8873b";

// ---------------------------------------------------------------- overlay (caption, cursor, highlight)
const OVERLAY = `
(() => {
  if (!document.body || document.getElementById('__cap')) return;
  const css = document.createElement('style');
  css.textContent = \`
    #__cap{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);max-width:1040px;z-index:2147483646;
      background:rgba(8,20,32,.86);color:#fff;font:600 21px/1.4 "Segoe UI","Noto Sans","DejaVu Sans",sans-serif;
      padding:12px 24px;border-radius:12px;text-align:center;box-shadow:0 8px 30px rgba(0,0,0,.35);
      border-bottom:3px solid ${GOLD};opacity:0;transition:opacity .35s;direction:ltr;pointer-events:none}
    #__cap.on{opacity:1}
    #__cur{position:fixed;left:0;top:0;width:26px;height:26px;z-index:2147483647;pointer-events:none;
      transform:translate(-3px,-2px);transition:transform .05s;filter:drop-shadow(0 2px 3px rgba(0,0,0,.45))}
    .__ripple{position:fixed;width:44px;height:44px;margin:-22px 0 0 -22px;border-radius:50%;z-index:2147483646;
      border:3px solid ${GOLD};pointer-events:none;animation:__rip .6s ease-out forwards}
    @keyframes __rip{from{transform:scale(.3);opacity:1}to{transform:scale(1.6);opacity:0}}
    .__hl{position:fixed;z-index:2147483645;pointer-events:none;border:3px solid ${GOLD};border-radius:12px;
      box-shadow:0 0 0 9999px rgba(8,20,32,.30),0 0 22px rgba(184,135,59,.9);animation:__hlin .3s ease}
    @keyframes __hlin{from{opacity:0}to{opacity:1}}
  \`;
  document.documentElement.appendChild(css);
  const cap = document.createElement('div'); cap.id='__cap'; document.documentElement.appendChild(cap);
  const cur = document.createElementNS('http://www.w3.org/2000/svg','svg');
  cur.id='__cur'; cur.setAttribute('viewBox','0 0 24 24');
  cur.innerHTML='<path d="M3 2l7 19 2.6-7.4L20 11z" fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/>';
  document.documentElement.appendChild(cur);
  const pos = window.__curPos || {x: ${W / 2}, y: ${H / 2}};
  cur.style.left = pos.x+'px'; cur.style.top = pos.y+'px';
  addEventListener('mousemove', e => { cur.style.left=e.clientX+'px'; cur.style.top=e.clientY+'px'; }, true);
  addEventListener('mousedown', e => { const r=document.createElement('div'); r.className='__ripple';
    r.style.left=e.clientX+'px'; r.style.top=e.clientY+'px'; document.documentElement.appendChild(r);
    setTimeout(()=>r.remove(),700); }, true);
  window.__cap = (t) => { cap.textContent = t || ''; cap.classList.toggle('on', !!t); };
  window.__hl = (sel, pad=8) => {
    document.querySelectorAll('.__hl').forEach(x=>x.remove());
    window.__hlEl = null;
    if (!sel) return;
    const el = typeof sel === 'string' ? document.querySelector(sel) : sel;
    if (!el) return;
    const h = document.createElement('div'); h.className='__hl';
    document.documentElement.appendChild(h);
    window.__hlEl = el;
    const place = () => {
      if (window.__hlEl !== el || !h.isConnected) return;
      const r = el.getBoundingClientRect();
      h.style.left=(r.left-pad)+'px'; h.style.top=(r.top-pad)+'px';
      h.style.width=(r.width+pad*2)+'px'; h.style.height=(r.height+pad*2)+'px';
      requestAnimationFrame(place);
    };
    place();
  };
})();`;

// ---------------------------------------------------------------- title cards
function card(inner, { dark = true } = {}) {
  return `<!doctype html><html><head><meta charset="utf-8"><style>
  *{box-sizing:border-box}html,body{margin:0;height:100%}
  body{font-family:"Segoe UI","Noto Sans","DejaVu Sans",sans-serif;display:flex;align-items:center;justify-content:center;
    background:${dark ? `radial-gradient(1200px 600px at 20% 0%,#145a85 0%,${NAVY} 45%,#06263a 100%)` : "#f4f6f9"};
    color:${dark ? "#fff" : "#14202e"}}
  .wrap{width:1060px;padding-bottom:70px}
  .brand{display:inline-block;background:${GOLD};color:#0b2233;font-weight:800;letter-spacing:.06em;padding:6px 14px;border-radius:8px;font-size:20px}
  h1{font-size:58px;line-height:1.1;margin:22px 0 14px;font-weight:800}
  h2{font-size:34px;margin:0 0 26px;font-weight:700}
  p.lead{font-size:24px;opacity:.88;margin:0 0 10px;line-height:1.45}
  .ar{font-size:26px;opacity:.85;direction:rtl;text-align:left;margin-top:6px}
  .rule{height:4px;width:120px;background:${GOLD};border-radius:2px;margin:26px 0}
  .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
  .box{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.18);border-radius:16px;padding:22px 22px 24px;opacity:0;transform:translateY(14px);animation:in .6s ease forwards}
  .box .k{font-size:40px;font-weight:800;color:#f1c27d}
  .box .t{font-size:19px;line-height:1.4;margin-top:6px;opacity:.92}
  .box:nth-child(2){animation-delay:1.2s}.box:nth-child(3){animation-delay:2.4s}
  @keyframes in{to{opacity:1;transform:none}}
  .muted{opacity:.7}
  .term{background:#0d1117;color:#d6e2ee;border-radius:14px;padding:22px 26px;font:17px/1.5 ui-monospace,Menlo,Consolas,"DejaVu Sans Mono",monospace;
    box-shadow:0 20px 50px rgba(0,0,0,.4);border:1px solid #30363d;white-space:pre}
  .term .p{color:#7ee787}.term .c{color:#f1c27d}.term .g{color:#7ee787;font-weight:700}.term .r{color:#ff7b72}
  .dots{display:flex;gap:7px;margin-bottom:14px}.dots i{width:12px;height:12px;border-radius:50%;background:#ff5f56}
  .dots i:nth-child(2){background:#ffbd2e}.dots i:nth-child(3){background:#27c93f}
  </style></head><body><div class="wrap">${inner}</div></body></html>`;
}

const TITLE = card(`
  <span class="brand">FAM</span>
  <h1>FAM Invoice Checker</h1>
  <p class="lead">AI-powered UAE VAT invoice compliance &amp; e-invoicing readiness</p>
  <p class="ar">التحقق من الفواتير الضريبية والجاهزية للفوترة الإلكترونية</p>
  <div class="rule"></div>
  <p class="lead muted">A proof of concept built for FAM Advisory, Dubai${PRESENTER ? ` · by ${PRESENTER}` : ""}</p>`);

const PROBLEM = card(`
  <h2>The problem</h2>
  <div class="grid">
    <div class="box"><div class="k">500+</div><div class="t">VAT clients. Every return starts with someone checking supplier invoices by hand — in English and Arabic.</div></div>
    <div class="box"><div class="k">1 error</div><div class="t">One invalid tax invoice means input VAT the client cannot recover — and an easy target in an FTA audit.</div></div>
    <div class="box"><div class="k">2027</div><div class="t">E-invoicing becomes mandatory: 1 Jan 2027 (revenue ≥ AED 50M), 1 Jul 2027 for everyone else.</div></div>
  </div>`);

function terminal(evalTail) {
  return card(`
  <h2>Same engine, from the terminal</h2>
  <div class="term"><div class="dots"><i></i><i></i><i></i></div><span class="p">$</span> famcheck demo      <span class="muted"># 14 invoices → Excel, Zoho CSV, EN/AR reports</span>
<span class="p">$</span> famcheck eval      <span class="muted"># golden-set accuracy check (runs in CI)</span>

${evalTail}</div>`);
}

const VALUE = card(`
  <h2>What this means for FAM</h2>
  <div class="grid">
    <div class="box"><div class="k">Team</div><div class="t">Invoice review before each VAT return drops from hours to minutes. Juniors handle exceptions, not data entry.</div></div>
    <div class="box"><div class="k">Clients</div><div class="t">VAT leakage is caught before filing — with clear reports in English and Arabic.</div></div>
    <div class="box"><div class="k">Growth</div><div class="t">A free “E-Invoicing Readiness Check” for the 2027 deadline — a lead magnet that opens paid advisory work.</div></div>
  </div>`);

const OUTRO = card(`
  <span class="brand">FAM</span>
  <h1>Ready for a 2-week pilot</h1>
  <p class="lead">1 · Tax team signs off the rule citations</p>
  <p class="lead">2 · Run on 50 anonymised real invoices and publish measured accuracy</p>
  <p class="lead">3 · Add OCR for photos, Zoho Books API and WhatsApp intake</p>
  <div class="rule"></div>
  <p class="lead muted">AI reads. Code decides. A human checks anything uncertain.${PRESENTER ? `<br>${PRESENTER} · AI &amp; Forward-Deployed Engineer` : ""}</p>`);

// ---------------------------------------------------------------- recorder
(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const evalTail = process.env.DEMO_EVAL_TEXT
    ? fs.readFileSync(process.env.DEMO_EVAL_TEXT, "utf8")
    : "Decision accuracy:        14/14 = 100.0%\nAuto-approved precision:  363/363 = 100.0%\nWrong values caught: 1   missed: 0";

  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: W, height: H }, deviceScaleFactor: 1,
    recordVideo: { dir: OUT, size: { width: W, height: H } },
  });
  const page = await context.newPage();
  const t0 = Date.now();
  const subs = [];
  let open = null;
  const now = () => (Date.now() - t0) / 1000;
  const sleep = (ms) => page.waitForTimeout(ms);

  async function ensure() { await page.evaluate(OVERLAY); }
  async function say(text, ms) {
    if (open) { open.end = now(); subs.push(open); open = null; }
    await page.evaluate((t) => window.__cap(t), text || "");
    if (text) open = { start: now(), text };
    if (ms) await sleep(ms);
  }
  async function hl(selector, pad) { await page.evaluate(([s, p]) => window.__hl(s, p), [selector || null, pad ?? 8]); }
  async function moveTo(selector, { click = false, offsetY = 0 } = {}) {
    const el = page.locator(selector).first();
    await el.scrollIntoViewIfNeeded();
    const b = await el.boundingBox();
    if (!b) return;
    const x = b.x + Math.min(b.width / 2, 60), y = b.y + b.height / 2 + offsetY;
    await page.mouse.move(x, y, { steps: 28 });
    await page.evaluate(([x, y]) => (window.__curPos = { x, y }), [x, y]);
    await sleep(250);
    if (click) { await page.mouse.down(); await sleep(90); await page.mouse.up(); }
  }
  async function go(url) {
    await page.goto(url, { waitUntil: "networkidle" });
    await ensure();
  }
  async function showCard(html) {
    await page.setContent(html, { waitUntil: "load" });
    await ensure();
  }
  async function smoothScroll(y, ms = 1200) {
    await page.evaluate(([y, ms]) => new Promise((res) => {
      const s = scrollY, d = y - s, t0 = performance.now();
      const f = (t) => { const k = Math.min(1, (t - t0) / ms); scrollTo(0, s + d * (0.5 - Math.cos(Math.PI * k) / 2)); k < 1 ? requestAnimationFrame(f) : res(); };
      requestAnimationFrame(f);
    }), [y, ms]);
  }

  // 1. Title
  await showCard(TITLE);
  await say("FAM Invoice Checker — a proof of concept built for FAM Advisory.", 4200);
  await say("It checks supplier invoices for UAE VAT compliance and 2027 e-invoicing readiness.", 4200);

  // 2. Problem
  await showCard(PROBLEM);
  await say("Every VAT return starts with someone checking supplier invoices by hand.", 3800);
  await say("One invalid tax invoice means input VAT the client cannot recover.", 3600);
  await say("And from 2027, e-invoicing becomes mandatory for every UAE business.", 4200);

  // 3. Home
  await go(BASE + "/?lang=en");
  await say("Here is the tool. The team uploads a client's invoices — PDF or photo, English or Arabic.", 600);
  await hl(".drop"); await moveTo(".drop"); await sleep(3600);
  await say("For this demo: 14 sample invoices for a fictitious restaurant group, Al Noor Restaurants.", 400);
  await hl("form.demo"); await moveTo("form.demo button"); await sleep(3000);
  await hl(null);
  await Promise.all([page.waitForURL(/\/batch\//), moveTo("form.demo button", { click: true })]);
  await page.waitForLoadState("networkidle");
  const batchUrl = page.url().split("?")[0];
  await ensure();

  // 4. Dashboard
  await say("In seconds, every invoice is checked: 4 valid, 2 need review, 8 have problems.", 500);
  await hl(".tiles .tile:nth-child(1)", 6); await sleep(900);
  await page.evaluate(() => { const t = document.querySelectorAll('.tiles .tile'); const a = t[0].getBoundingClientRect(), b = t[3].getBoundingClientRect();
    window.__hlEl = null; const h = document.querySelector('.__hl'); h.style.left = (a.left - 8) + 'px'; h.style.width = (b.right - a.left + 16) + 'px'; });
  await sleep(3200);
  await say("AED 1,998 of input VAT is at risk — found before the VAT return is filed.", 300);
  await hl(".tiles .tile.wide:nth-of-type(5)"); await moveTo(".tiles .tile.wide >> nth=0"); await sleep(3800);
  await say("Only 21% of these invoices are ready for e-invoicing — a ready-made advisory conversation.", 300);
  await hl(".tiles .tile.wide:nth-of-type(6)"); await moveTo(".tiles .tile.wide >> nth=1"); await sleep(4200);
  await hl(null);
  await say("Each invoice gets a clear status and the exact reason — in plain language.", 300);
  await smoothScroll(330, 1600); await sleep(600);
  await hl("table.list tbody tr:nth-child(4)", 2); await moveTo("table.list tbody tr:nth-child(4) td.issues"); await sleep(2600);
  await hl("table.list tbody tr:nth-child(7)", 2); await moveTo("table.list tbody tr:nth-child(7) td.issues"); await sleep(2000);
  await smoothScroll(620, 1400);
  await hl("table.list tbody tr:nth-child(11)", 2); await moveTo("table.list tbody tr:nth-child(11) td.issues"); await sleep(2600);
  await hl(null);

  // 5. VAT wrong (inv04)
  await say("Let's open one. This supplier printed VAT of AED 125.00.", 200);
  await Promise.all([page.waitForURL(/invoice\/3/), moveTo("table.list tbody tr:nth-child(4) a", { click: true })]);
  await page.waitForLoadState("networkidle"); await ensure(); await sleep(1500);
  await say("The tool recomputes it: 5% of 2,400.00 is 120.00. All maths is done by code — never by AI.", 300);
  await hl(".finding"); await moveTo(".finding"); await sleep(4800);
  await say("Every finding cites its legal basis, so the team can explain it to the client.", 300);
  await hl(".finding .muted", 4); await sleep(3600);
  await say("On the right: the original invoice, for a quick visual check.", 300);
  await hl(".doc"); await moveTo(".doc-view img"); await sleep(3200); await hl(null);

  // 6. Arabic invoice (inv02)
  await go(batchUrl + "/invoice/1?lang=en");
  await say("Arabic invoices work natively — including Arabic-Indic digits like ١٠٠٤٥٦…", 300);
  await hl(".doc"); await moveTo(".doc-view img"); await sleep(3800);
  await smoothScroll(420, 1400);
  await say("Every value shows the exact text it was read from, verified against the document itself.", 300);
  await hl("table.fields tbody tr.fs-verified:nth-child(8)", 2); await moveTo("table.fields tbody tr:nth-child(8) td.ev"); await sleep(4600);
  await hl(null);

  // 7. Guardrail (inv14)
  await go(batchUrl + "/invoice/13?lang=en");
  await say("What if the AI misreads a single digit? We simulated exactly that here.", 300);
  await sleep(3400);
  await say("The TRN it read is not in the document, so it is thrown away and sent to a person.", 300);
  await hl(".finding"); await moveTo(".finding"); await sleep(4200);
  await smoothScroll(520, 1300);
  await hl("tr.fs-unverified", 2); await moveTo("tr.fs-unverified td.ev");
  await say("The tool never guesses. Uncertain means 'needs review' — never a false green tick.", 4800);
  await hl(null);

  // 8. Photo (inv12)
  await go(batchUrl + "/invoice/11?lang=en");
  await say("Phone photos can't be machine-verified, so they are never auto-approved.", 300);
  await page.evaluate(() => window.__hl([...document.querySelectorAll('.finding')].find(f => f.textContent.includes('GUARD-002'))));
  await moveTo(".doc-view img"); await sleep(3800); await hl(null);

  // 9. Arabic UI
  await go(batchUrl + "?lang=en");
  await say("One click switches the entire app to Arabic, right-to-left.", 300);
  await hl("a.lang", 6); await moveTo("a.lang"); await sleep(1600);
  await Promise.all([page.waitForURL(/lang=ar/), moveTo("a.lang", { click: true })]);
  await page.waitForLoadState("networkidle"); await ensure(); await sleep(4200);

  // 10. Client report
  await go(batchUrl + "/report?lang=en");
  await say("And a client-ready report: VAT at risk, readiness score, deadlines and next steps.", 300);
  await sleep(3200); await smoothScroll(520, 2200); await sleep(1800); await smoothScroll(1150, 2200); await sleep(1600);
  await go(batchUrl + "/report?lang=ar");
  await say("The same report in Arabic — ready to send to the client.", 4200);

  // 11. Exports
  await go(batchUrl + "?lang=en");
  await say("Excel for the team, and a Zoho Books file with valid invoices only — bad data never reaches the books.", 300);
  await hl(".dl", 8); await moveTo(".dl a:nth-child(3)"); await sleep(5200); await hl(null);

  // 12. Rules
  await go(BASE + "/rules?lang=en");
  await say("The rules are plain files your tax team can review and sign off — no code needed.", 300);
  await hl("section.card:nth-of-type(1)"); await moveTo("section.card:nth-of-type(1) h2"); await sleep(4400); await hl(null);

  // 13. Terminal
  await showCard(terminal(evalTail));
  await say("The same engine runs from the terminal, with an accuracy check on every change.", 4200);
  await say("14 of 14 decisions correct. The simulated AI misread caught. Zero wrong values auto-approved.", 4800);

  // 14. Value + outro
  await showCard(VALUE);
  await say("For the team: hours of invoice checking become minutes.", 3200);
  await say("For clients: VAT leakage caught before filing, in English and Arabic.", 3200);
  await say("For FAM: a free e-invoicing readiness check that opens new advisory work.", 3800);
  await showCard(OUTRO);
  await say("Next step: a two-week pilot on real FAM invoices. Thank you.", 5200);
  await say("", 600);

  const video = page.video();
  await context.close();
  await browser.close();
  const src = await video.path();
  fs.renameSync(src, path.join(OUT, "demo.webm"));

  const ts = (s) => { const ms = Math.round(s * 1000); const h = Math.floor(ms / 3600000), m = Math.floor(ms / 60000) % 60, sec = Math.floor(ms / 1000) % 60;
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")},${String(ms % 1000).padStart(3, "0")}`; };
  const srt = subs.map((s, i) => `${i + 1}\n${ts(s.start)} --> ${ts(s.end)}\n${s.text}\n`).join("\n");
  fs.writeFileSync(path.join(OUT, "demo.srt"), srt);
  console.log(`video: ${path.join(OUT, "demo.webm")}  (${now().toFixed(1)}s, ${subs.length} captions)`);
})();
