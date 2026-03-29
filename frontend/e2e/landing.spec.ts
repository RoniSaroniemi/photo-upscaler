import { test, expect } from '@playwright/test';

test.describe('Landing page', () => {
  test('renders upload area', async ({ page }) => {
    await page.goto('/');
    const dropZone = page.getByText(/drag.*drop|upload|choose.*file/i).first();
    await expect(dropZone).toBeVisible();
  });

  test('pricing info is visible', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText(/cost|price|per megapixel|\$/i).first()).toBeVisible();
  });

  test('shows how it works section', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText(/how it works/i)).toBeVisible();
  });

  test('shows example costs', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText(/example/i).first()).toBeVisible();
  });
});
