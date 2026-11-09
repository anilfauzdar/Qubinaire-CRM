import { chromium } from 'playwright';
const portal = process.env.PORTAL_BASE || 'http://127.0.0.1:5001';
const username = process.env.CRM_USERNAME;
const password = process.env.CRM_PASSWORD;
if (!username || !password) throw new Error('Set CRM_USERNAME and CRM_PASSWORD for a staging account');
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  const response = await page.goto(portal, { waitUntil: 'domcontentloaded' });
  if (!response || response.status() >= 500) throw new Error('Portal did not respond');
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.waitForURL('**/dashboard', { timeout: 15000 });
  await page.getByRole('heading', { name: 'Dashboard' }).waitFor();
  await page.getByRole('link', { name: 'Leads' }).click();
  await page.getByRole('heading', { name: 'Leads' }).waitFor();
  console.log('Browser smoke test PASS: login, dashboard, leads');
} finally {
  await browser.close();
}
