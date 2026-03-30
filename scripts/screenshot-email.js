const { chromium } = require("playwright");
const fs = require("fs");

const emailData = JSON.parse(
  fs.readFileSync("evidence/email-magic-link/email-content.json", "utf-8")
);

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 600, height: 800 } });
  await page.setContent(emailData.html);
  await page.screenshot({
    path: "evidence/email-magic-link/email-rendered.png",
    fullPage: true,
  });
  await browser.close();
  console.log("Screenshot saved to evidence/email-magic-link/email-rendered.png");
})();
