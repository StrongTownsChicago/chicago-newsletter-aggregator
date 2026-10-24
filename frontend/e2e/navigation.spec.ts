import { test, expect, type Page } from '@playwright/test';

function primaryNav(page: Page) {
  return page.getByRole('navigation', { name: 'Primary' });
}

test('can navigate to search', async ({ page }) => {
  await page.goto('/');
  await primaryNav(page).getByRole('link', { name: 'Search' }).click();
  await expect(page).toHaveURL(/.*search/);
  await expect(page.getByTestId('search-input')).toBeVisible();
});

test('can navigate to login', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('signin-link').click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('heading', { name: 'Sign in', level: 1 })).toBeVisible();
});

test('can navigate back home from search', async ({ page }) => {
  await page.goto('/search');
  await primaryNav(page).getByRole('link', { name: 'Recent' }).click();
  await expect(page).toHaveURL(/\/$/);
});

test('can navigate to the ward directory', async ({ page }) => {
  await page.goto('/');
  await primaryNav(page).getByRole('link', { name: 'Wards' }).click();
  await expect(page).toHaveURL(/\/wards$/);
  await expect(page.getByTestId('ward-directory')).toBeVisible();
});

for (const [path, activeLabel] of [
  ['/', 'Recent'],
  ['/search', 'Search'],
  ['/wards', 'Wards'],
  ['/ward/1', 'Wards'],
]) {
  test(`marks ${activeLabel} as the current page on ${path}`, async ({ page }) => {
    await page.goto(path);
    const currentLinks = primaryNav(page).locator('a[aria-current="page"]');
    await expect(currentLinks).toHaveCount(1);
    await expect(currentLinks).toHaveText(activeLabel);
  });
}
