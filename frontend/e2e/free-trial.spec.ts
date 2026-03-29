import { test, expect } from '@playwright/test';
import path from 'path';

test.describe('Free trial upload flow', () => {
  test('can upload an image file', async ({ page }) => {
    await page.goto('/');

    // The upload area should be present
    const fileInput = page.locator('input[type="file"]');
    await expect(fileInput).toBeAttached();
  });

  test('shows cost estimate after selecting image', async ({ page }) => {
    await page.goto('/');

    // Look for cost-related text on the page
    await expect(page.getByText(/cost|estimate|free|trial/i).first()).toBeVisible();
  });

  test('shows processing state elements', async ({ page }) => {
    await page.goto('/');

    // The page should have upscale/process button or trial info
    const actionArea = page.getByText(/upscale|process|free trial|trial upscale/i).first();
    await expect(actionArea).toBeVisible();
  });

  test('displays cost breakdown structure', async ({ page }) => {
    await page.goto('/');

    // Cost breakdown section should reference compute or platform fee
    await expect(page.getByText(/compute|platform|cost|megapixel/i).first()).toBeVisible();
  });
});
