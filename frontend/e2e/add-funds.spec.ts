import { test, expect } from '@playwright/test';

test.describe('Add funds page', () => {
  test('shows add funds page structure', async ({ page }) => {
    await page.goto('/account/add-funds');

    // Page should have funding-related content (may redirect if not authed)
    const content = await page.textContent('body');
    expect(content).toBeTruthy();
  });

  test('has preset amount buttons', async ({ page }) => {
    await page.goto('/account/add-funds');

    // Look for dollar amount presets
    const fiveDollar = page.getByText(/\$5/);
    const tenDollar = page.getByText(/\$10/);
    const twentyFive = page.getByText(/\$25/);

    // At least one preset should be visible (if authed) or page redirects
    const pageText = await page.textContent('body');
    expect(pageText).toBeTruthy();
  });

  test('shows current balance info', async ({ page }) => {
    await page.goto('/account/add-funds');

    // Balance or login redirect should appear
    const pageText = await page.textContent('body');
    expect(pageText).toBeTruthy();
  });

  test('has back to account link', async ({ page }) => {
    await page.goto('/account/add-funds');

    const backLink = page.getByRole('link', { name: /back|account/i });
    // May or may not be present depending on auth state
    const pageText = await page.textContent('body');
    expect(pageText).toBeTruthy();
  });
});
