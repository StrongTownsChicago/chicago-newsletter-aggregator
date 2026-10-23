import { test, expect } from '@playwright/test';

test('shows empty state message for no search results', async ({ page }) => {
  // Use a random string likely to return no results
  const randomQuery = `noresultsfound_${Math.random().toString(36).substring(7)}`;
  await page.goto(`/search?q=${randomQuery}`);

  await expect(page.getByTestId('search-empty')).toContainText('No newsletters match your search');
  await expect(page.getByTestId('newsletter-card')).toHaveCount(0);
});

test('a missing newsletter is a 404 at its own URL', async ({ page }) => {
  const url = '/newsletter/00000000-0000-0000-0000-000000000000';
  const response = await page.goto(url);
  expect(response?.status()).toBe(404);
  await expect(page).toHaveURL(url);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Newsletter not found');
});

test('a malformed newsletter id is a 404', async ({ page }) => {
  const response = await page.goto('/newsletter/not-a-newsletter');
  expect(response?.status()).toBe(404);
  await expect(page.getByTestId('not-found')).toBeVisible();
});

test('an unknown page shows the 404 page', async ({ page }) => {
  const response = await page.goto('/no-such-page');
  expect(response?.status()).toBe(404);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Page not found');
  await expect(page.getByRole('search')).toBeVisible();
});

test('an invalid page number falls back to the first page', async ({ page }) => {
  await page.goto('/?page=abc');
  await expect(page.getByTestId('newsletter-card').first()).toBeVisible();
});
