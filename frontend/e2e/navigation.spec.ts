import { test, expect } from '@playwright/test';

test('can navigate to search', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('link', { name: /search/i }).first().click();
  await expect(page).toHaveURL(/.*search/);
  await expect(page.getByTestId('search-input')).toBeVisible();
});

test('can navigate to login', async ({ page }) => {
  await page.goto('/');
  const signinLink = page.getByTestId('signin-link');
  
  if (await signinLink.count() > 0) {
      await signinLink.click();
      await expect(page).toHaveURL(/.*login/);
      await expect(page.locator('form')).toBeVisible();
  }
});

test('can navigate back home from search', async ({ page }) => {
  await page.goto('/search');
  await page.getByRole('link', { name: /recent/i }).first().click();
  await expect(page).toHaveURL(/\/$/);
});