import { test, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';

const EVIDENCE_DIR = path.join(__dirname, '../../evidence/auth-journey/');
// Use unique email per run to avoid rate limiting (3 per email per hour)
const RUN_ID = Date.now();
const TEST_EMAIL = `test-journey-${RUN_ID}@honest-image-tools.local`;

test.describe('Auth Journey Screenshots', () => {
  test.beforeAll(() => {
    fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
  });

  test('01 - Homepage', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('header').getByText('Honest Image Tools')).toBeVisible();
    await page.screenshot({ path: path.join(EVIDENCE_DIR, '01-homepage.png'), fullPage: true });
  });

  test('02 - Login Page', async ({ page }) => {
    await page.goto('/auth/login');
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Send magic link' })).toBeVisible();
    await page.screenshot({ path: path.join(EVIDENCE_DIR, '02-login-page.png'), fullPage: true });
  });

  test('03 - Check Email State', async ({ page }) => {
    await page.goto('/auth/login');
    await page.locator('input[type="email"]').fill(TEST_EMAIL);
    await page.getByRole('button', { name: 'Send magic link' }).click();
    await expect(page.getByRole('heading', { name: 'Check your email' })).toBeVisible({ timeout: 15000 });
    await page.screenshot({ path: path.join(EVIDENCE_DIR, '03-check-email.png'), fullPage: true });
  });

  test('04 - Email Rendered', async ({ page, context }) => {
    // Use a different email to avoid rate limit from test 03
    const emailForTest4 = `test-email-${RUN_ID}@honest-image-tools.local`;
    await page.goto('/auth/login');
    await page.locator('input[type="email"]').fill(emailForTest4);
    await page.getByRole('button', { name: 'Send magic link' }).click();
    await expect(page.getByRole('heading', { name: 'Check your email' })).toBeVisible({ timeout: 15000 });

    // Fetch the last captured email
    const response = await page.request.get('/api/test/auth/last-email');
    expect(response.ok()).toBeTruthy();
    const emailData = await response.json();
    expect(emailData.html).toBeTruthy();

    // Render email HTML in a new page
    const emailPage = await context.newPage();
    await emailPage.setContent(emailData.html);
    await emailPage.screenshot({ path: path.join(EVIDENCE_DIR, '04-email-rendered.png'), fullPage: true });
    await emailPage.close();
  });

  test('05 - Verify Landing', async ({ page }) => {
    // Get a fresh magic link token via test API
    const tokenResponse = await page.request.post('/api/test/auth/magic-link', {
      data: { email: TEST_EMAIL },
    });
    expect(tokenResponse.ok()).toBeTruthy();
    const { verifyUrl } = await tokenResponse.json();

    // Navigate to the verify URL (sets session cookie, redirects to /account)
    await page.goto(verifyUrl);
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: path.join(EVIDENCE_DIR, '05-verify-landing.png'), fullPage: true });
  });

  test('06 - Authenticated Account', async ({ page }) => {
    // First authenticate via dev-login test endpoint
    const loginResponse = await page.request.post('/api/test/auth/dev-login', {
      data: { email: TEST_EMAIL },
    });
    expect(loginResponse.ok()).toBeTruthy();

    // Navigate to account page
    await page.goto('/account');
    await expect(page.getByRole('heading', { name: 'Account' })).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Balance')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Log Out' })).toBeVisible();
    await page.screenshot({ path: path.join(EVIDENCE_DIR, '06-authenticated.png'), fullPage: true });
  });
});
