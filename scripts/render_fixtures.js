// Renders fixtures/_build/*.html into PDFs (text layer) or a PNG "photo" (no text layer).
// Usage: node scripts/render_fixtures.js   (needs the `playwright` npm package + Chromium)
const path = require("path");
const fs = require("fs");
const { chromium } = require("playwright");

(async () => {
  const jobs = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "fixtures", "_build", "jobs.json"), "utf8"));
  const browser = await chromium.launch();
  for (const job of jobs) {
    fs.mkdirSync(path.dirname(job.out), { recursive: true });
    if (job.type === "png") {
      const page = await browser.newPage({ viewport: { width: 760, height: 900 }, deviceScaleFactor: 1 });
      await page.goto("file://" + job.html);
      // make it look like a phone photo of a printed receipt
      await page.addStyleTag({ content: "body{transform:rotate(-1.2deg);filter:contrast(.92) brightness(.97) sepia(.08);background:#f4f1ea}" });
      await page.screenshot({ path: job.out, fullPage: true });
      await page.close();
    } else {
      const page = await browser.newPage();
      await page.goto("file://" + job.html);
      await page.pdf({ path: job.out, format: "A4", printBackground: true });
      await page.close();
    }
    console.log("rendered", path.basename(job.out));
  }
  await browser.close();
})();
