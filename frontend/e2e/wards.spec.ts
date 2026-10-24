import { test, expect } from '@playwright/test';
import { FEATURED_NEWSLETTER, WARD_1, WARD_40, WARD_WITHOUT_ALDERMAN } from './fixtures/db/facts';

test('ward directory lists all 50 wards with their aldermen and links to ward pages', async ({ page }) => {
  await page.goto('/wards');

  const wardLinks = page.getByTestId('ward-directory-link');
  await expect(wardLinks).toHaveCount(50);
  await expect(wardLinks.nth(WARD_40.ward - 1)).toContainText(WARD_40.aldermen.join(' and '));
  await expect(wardLinks.nth(WARD_WITHOUT_ALDERMAN - 1)).toContainText('No alderman on file');

  await wardLinks.first().click();
  await expect(page).toHaveURL(/\/ward\/1$/);
  await expect(page.getByTestId('ward-title')).toHaveText(`1st Ward Alderman ${WARD_1.alderman}`);
});

test('ward page shows the alderman, newsletter count and a link to filtered search', async ({ page }) => {
  await page.goto(`/ward/${WARD_1.ward}`);

  await expect(page.getByTestId('ward-stats')).toContainText(`${WARD_1.newsletters} newsletters`);
  await expect(page.getByTestId('ward-stats')).toContainText(`Latest ${FEATURED_NEWSLETTER.receivedDate}`);
  await expect(page.getByTestId('ward-search-link')).toHaveAttribute('href', `/search?ward=${WARD_1.ward}`);
  await expect(page.getByTestId('newsletter-card')).toHaveCount(WARD_1.newsletters);
});

test('a ward with two aldermen lists both and merges their newsletters', async ({ page }) => {
  await page.goto(`/ward/${WARD_40.ward}`);

  await expect(page.getByTestId('ward-title')).toHaveText(`40th Ward Aldermen ${WARD_40.aldermen.join(' and ')}`);
  await expect(page.getByTestId('ward-alder')).toHaveCount(WARD_40.aldermen.length);
  await expect(page.getByTestId('ward-stats')).toContainText(`${WARD_40.newsletters} newsletters`);

  const cards = page.getByTestId('newsletter-card');
  await expect(cards).toHaveCount(WARD_40.newsletters);
  await expect(cards.first().getByTestId('newsletter-title')).toHaveText(WARD_40.latestSubject);
  await expect(cards.filter({ hasText: WARD_40.formerAldermanSubject })).toHaveCount(1);
});

test('a ward without an alderman on file says so', async ({ page }) => {
  await page.goto(`/ward/${WARD_WITHOUT_ALDERMAN}`);

  await expect(page.getByTestId('ward-no-alder')).toBeVisible();
  await expect(page.getByTestId('ward-empty')).toBeVisible();
  await expect(page.getByTestId('ward-search-link')).toHaveCount(0);
});

test('ward page names the ward the way people search and carries breadcrumb structured data', async ({ page }) => {
  await page.goto('/ward/1');

  await expect(page).toHaveTitle(/^1st Ward/);
  await expect(page.getByTestId('ward-title')).toContainText('1st Ward');
  const structuredData = JSON.parse(
    (await page.locator('head script[type="application/ld+json"]').textContent()) ?? '{}',
  ) as { '@graph'?: { '@type': string }[] };
  expect(structuredData['@graph']?.[0]['@type']).toBe('BreadcrumbList');
});

test('newsletter card ward badge links to the ward page', async ({ page }) => {
  await page.goto('/');

  await page.getByTestId('newsletter-ward-link').first().click();
  await expect(page).toHaveURL(new RegExp(`/ward/${FEATURED_NEWSLETTER.ward}$`));
  await expect(page.getByTestId('ward-header')).toBeVisible();
});

for (const invalidWard of ['0', '51', 'abc', '05']) {
  test(`invalid ward "${invalidWard}" responds 404`, async ({ page }) => {
    const response = await page.goto(`/ward/${invalidWard}`);
    expect(response?.status()).toBe(404);
    await expect(page.getByTestId('ward-not-found')).toBeVisible();
    await expect(page.locator('script[type="application/ld+json"]')).toHaveCount(0);
  });
}
