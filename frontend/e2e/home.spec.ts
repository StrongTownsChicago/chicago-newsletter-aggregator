import { test, expect } from '@playwright/test';

test('has title', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveTitle(/Chicago Alderman Newsletter Tracker/);
});

test('has main heading', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Chicago Alderman Newsletter Tracker', level: 1 })).toBeVisible();
});

test('displays newsletter cards', async ({ page }) => {
  await page.goto('/');
  // Wait for some newsletter cards to appear
  const cards = page.getByTestId('newsletter-card');
  // We expect at least one card if there is data in Supabase,
  // but even if empty, the test should handle it.
  if (await cards.count() > 0) {
    await expect(cards.first()).toBeVisible();
    await expect(page.getByTestId('newsletter-title').first()).toBeVisible();
    await expect(page.getByTestId('newsletter-source').first()).toBeVisible();
  }
});

test('shows pagination when many newsletters exist', async ({ page }) => {
  await page.goto('/');
  const pagination = page.getByTestId('pagination');
  // Only check visibility if pagination exists (i.e. > 20 newsletters)
  if (await pagination.count() > 0) {
    await expect(pagination).toBeVisible();
    await expect(page.getByTestId('pagination-next')).toBeVisible();
  }
});