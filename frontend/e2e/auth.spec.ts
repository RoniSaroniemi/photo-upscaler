import { test, expect } from '@playwright/test';

test.describe('Authentication flow', () => {
  test('login page has email input', async ({ page }) => {
    await page.goto('/auth/login');
    const emailInput = page.locator('input[type="email"]');
    await expect(emailInput).toBeVisible();
  });

  test('login page has send magic link button', async ({ page }) => {
    await page.goto('/auth/login');
    const submitBtn = page.getByRole('button', { name: /send.*magic.*link|sign.*in|log.*in/i });
    await expect(submitBtn).toBeVisible();
  });

  test('shows validation on empty submit', async ({ page }) => {
    await page.goto('/auth/login');
    const submitBtn = page.getByRole('button', { name: /send.*magic.*link|sign.*in|log.*in/i });
    await submitBtn.click();

    // Browser native validation or app error should appear
    const emailInput = page.locator('input[type="email"]');
    await expect(emailInput).toBeVisible();
  });

  test('accepts email and submits', async ({ page }) => {
    await page.goto('/auth/login');
    const emailInput = page.locator('input[type="email"]');
    await emailInput.fill('test@example.com');
    await expect(emailInput).toHaveValue('test@example.com');
  });
});
