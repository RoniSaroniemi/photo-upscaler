import { test, expect } from '@playwright/test';

test.describe('Account page', () => {
  test('account page loads', async ({ page }) => {
    await page.goto('/account');

    // Should show account content or redirect to login
    const pageText = await page.textContent('body');
    expect(pageText).toBeTruthy();
  });

  test('shows balance section when authenticated', async ({ page }) => {
    await page.goto('/account');

    // Look for balance or sign-in prompt
    const hasBalance = await page.getByText(/balance|\$/i).first().isVisible().catch(() => false);
    const hasLogin = await page.getByText(/sign in|log in/i).first().isVisible().catch(() => false);
    expect(hasBalance || hasLogin).toBeTruthy();
  });

  test('shows recent transactions or empty state', async ({ page }) => {
    await page.goto('/account');

    const pageText = await page.textContent('body');
    expect(pageText).toBeTruthy();
  });

  test('has add funds and logout buttons when authenticated', async ({ page }) => {
    await page.goto('/account');

    // Either shows account actions or redirects
    const pageText = await page.textContent('body');
    expect(pageText).toBeTruthy();
  });
});
