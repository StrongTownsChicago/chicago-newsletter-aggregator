import { test, expect } from '@playwright/test';

test('ward directory lists all 50 wards and links to ward pages', async ({ page }) => {
  await page.goto('/wards');

  const wardLinks = page.getByTestId('ward-directory-link');
  await expect(wardLinks).toHaveCount(50);

  await wardLinks.first().click();
  await expect(page).toHaveURL(/\/ward\/1$/);
  await expect(page.getByTestId('ward-header')).toBeVisible();
});

test('ward page shows the alderman header and links to filtered search', async ({ page }) => {
  await page.goto('/ward/1');

  await expect(page.getByTestId('ward-title')).toBeVisible();
  const searchLink = page.getByTestId('ward-search-link');
  if ((await searchLink.count()) > 0) {
    await expect(searchLink).toHaveAttribute('href', '/search?ward=1');
  } else {
    await expect(page.getByTestId('ward-empty')).toBeVisible();
  }
});

test('newsletter card ward badge links to the ward page', async ({ page }) => {
  await page.goto('/');

  const wardLink = page.getByTestId('newsletter-ward-link').first();
  if ((await wardLink.count()) === 0) {
    test.skip(true, 'No newsletters with a ward to link from');
  }
  const href = await wardLink.getAttribute('href');
  await wardLink.click();
  await expect(page).toHaveURL(new RegExp(`${href}$`));
  await expect(page.getByTestId('ward-header')).toBeVisible();
});

for (const invalidWard of ['0', '51', 'abc', '05']) {
  test(`invalid ward "${invalidWard}" responds 404`, async ({ page }) => {
    const response = await page.goto(`/ward/${invalidWard}`);
    expect(response?.status()).toBe(404);
    await expect(page.getByTestId('ward-not-found')).toBeVisible();
  });
}
