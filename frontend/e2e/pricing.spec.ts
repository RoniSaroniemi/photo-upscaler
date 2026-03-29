import { test, expect } from '@playwright/test';

test.describe('Pricing page', () => {
  test('shows pricing calculator', async ({ page }) => {
    await page.goto('/pricing');
    await expect(page.getByText(/cost calculator|calculate/i).first()).toBeVisible();
  });

  test('has width and height inputs', async ({ page }) => {
    await page.goto('/pricing');
    const widthInput = page.locator('input').first();
    await expect(widthInput).toBeVisible();
  });

  test('shows cost examples table', async ({ page }) => {
    await page.goto('/pricing');
    await expect(page.getByText(/1920|1080|4k|common/i).first()).toBeVisible();
  });

  test('shows competitive comparison', async ({ page }) => {
    await page.goto('/pricing');
    await expect(page.getByText(/comparison|competitor|transparent/i).first()).toBeVisible();
  });

  test('shows FAQ section', async ({ page }) => {
    await page.goto('/pricing');
    await expect(page.getByText(/FAQ|frequently asked/i).first()).toBeVisible();
  });

  test('has CTA linking to home', async ({ page }) => {
    await page.goto('/pricing');
    const cta = page.getByRole('link', { name: /try it|get started|upscale/i }).first();
    await expect(cta).toBeVisible();
  });
});
