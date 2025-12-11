const puppeteer = require('puppeteer');

const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));

(async () => {
  const browser = await puppeteer.launch({headless: true, args: ['--no-sandbox', '--disable-setuid-sandbox']});
  const page = await browser.newPage();
  page.on('requestfinished', req => {
    if (req.url().includes('/api/v1/history/requests')) {
      console.log('History request finished with status', req.response()?.status());
    }
  });
  await page.goto('http://localhost:8000', {waitUntil: 'networkidle2'});
  await page.waitForSelector('.tab-button[data-tab="history"]');
  await page.click('.tab-button[data-tab="history"]');
  await delay(6000);
  const rows = await page.$$eval('#historyTableBody tr', rows => rows.map(row => row.textContent.trim()));
  console.log('Rows:', rows);
  await browser.close();
})();
