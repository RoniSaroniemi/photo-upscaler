import { test, expect } from '@playwright/test';

test.use({ viewport: { width: 375, height: 667 } });

test.describe('Mobile responsiveness', () => {
  test('landing page renders at 375px', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('body')).toBeVisible();

    // Upload area should still be accessible
    const fileInput = page.locator('input[type="file"]');
    await expect(fileInput).toBeAttached();
  });

  test('pricing page renders at 375px', async ({ page }) => {
    await page.goto('/pricing');
    await expect(page.locator('body')).toBeVisible();
    await expect(page.getByText(/cost|price|calculator/i).first()).toBeVisible();
  });

  test('login page renders at 375px', async ({ page }) => {
    await page.goto('/auth/login');
    await expect(page.locator('body')).toBeVisible();

    const emailInput = page.locator('input[type="email"]');
    await expect(emailInput).toBeVisible();
  });

  test('account page renders at 375px', async ({ page }) => {
    await page.goto('/account');
    await expect(page.locator('body')).toBeVisible();
  });

  test('add funds page renders at 375px', async ({ page }) => {
    await page.goto('/account/add-funds');
    await expect(page.locator('body')).toBeVisible();
  });

  test('no horizontal overflow on landing', async ({ page }) => {
    await page.goto('/');
    const body = page.locator('body');
    const bodyWidth = await body.evaluate(el => el.scrollWidth);
    expect(bodyWidth).toBeLessThanOrEqual(375 + 1); // 1px tolerance
  });
});
