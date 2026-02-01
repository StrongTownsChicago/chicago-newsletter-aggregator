import { test, expect } from '@playwright/test';

test('can perform keyword search', async ({ page }) => {
  await page.goto('/search');
  
  const searchInput = page.getByTestId('search-input');
  await searchInput.fill('zoning');
  await page.getByTestId('search-button').click();
  
  await expect(page).toHaveURL(/.*q=zoning/);
});

test('can filter by ward', async ({ page }) => {
  await page.goto('/search');
  
  const wardFilter = page.getByTestId('ward-filter');
  // Check if options exist
  const options = await wardFilter.locator('option').count();
  if (options > 1) {
    const firstWard = await wardFilter.locator('option').nth(1).getAttribute('value');
    if (firstWard) {
        await wardFilter.selectOption(firstWard);
        await page.getByTestId('search-button').click();
        await expect(page).toHaveURL(new RegExp(`.*ward=${firstWard}`));
    }
  }
});

test('can clear filters', async ({ page }) => {
  await page.goto('/search?q=test&ward=1');
  await expect(page.getByTestId('search-input')).toHaveValue('test');
  
  await page.getByTestId('clear-filters-link').click();
  await expect(page).toHaveURL(/\/search$/);
  await expect(page.getByTestId('search-input')).toHaveValue('');
});
