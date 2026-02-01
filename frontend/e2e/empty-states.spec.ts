import { test, expect } from '@playwright/test';

test('shows empty state message for no search results', async ({ page }) => {
  // Use a random string likely to return no results
  const randomQuery = `noresultsfound_${Math.random().toString(36).substring(7)}`;
  await page.goto(`/search?q=${randomQuery}`);
  
  await expect(page.getByText(/No newsletters found matching your criteria/i)).toBeVisible();
  await expect(page.getByTestId('newsletter-card')).toHaveCount(0);
});

test('handles non-existent newsletter ID gracefully', async ({ page }) => {
  // Navigation to a non-existent ID should redirect to 404 per the code in [id].astro
  await page.goto('/newsletter/00000000-0000-0000-0000-000000000000');
  await expect(page).toHaveURL(/\/404/);
});
