import { test, expect, type Page } from '@playwright/test';
import { FEATURED_NEWSLETTER } from './fixtures/db/facts';

async function expectSiteHeaderAndFooter(page: Page) {
  const header = page.getByRole('banner');
  await expect(header).toBeVisible();
  await expect(header.getByTestId('site-name')).toHaveAttribute('href', '/');
  await expect(header.getByTestId('site-tagline')).toBeVisible();
  // Only the homepage uses the site name as its h1; covered by the per-path h1 test.
  if (new URL(page.url()).pathname !== '/') {
    await expect(header.locator('h1')).toHaveCount(0);
  }
  await expect(header.getByTestId('header-github-link')).toHaveAttribute(
    'href',
    'https://github.com/StrongTownsChicago/chicago-newsletter-aggregator',
  );
  await expect(page.getByRole('navigation', { name: 'Primary' })).toBeVisible();

  const footer = page.getByRole('contentinfo');
  await expect(footer).toBeVisible();
  await expect(footer.getByTestId('site-footer-credit')).toHaveText('Built for Strong Towns Chicago');
  await expect(footer.getByTestId('site-footer-stc-link')).toHaveAttribute(
    'href',
    'https://www.strongtownschicago.org/',
  );
  await expect(footer.getByTestId('site-footer-source-link')).toHaveAttribute(
    'href',
    'https://github.com/StrongTownsChicago/chicago-newsletter-aggregator',
  );
}

for (const path of ['/', '/search', '/wards', '/ward/1']) {
  test(`renders the site header and footer on ${path}`, async ({ page }) => {
    await page.goto(path);
    await expectSiteHeaderAndFooter(page);
  });

  test(`has one main landmark and one h1 on ${path}`, async ({ page }) => {
    await page.goto(path);
    await expect(page.getByRole('main')).toHaveCount(1);
    await expect(page.locator('h1')).toHaveCount(1);
    const h1Container = path === '/' ? page.getByRole('banner') : page.getByRole('main');
    await expect(h1Container.locator('h1')).toHaveCount(1);
  });
}

test('renders the site header and footer on a newsletter detail page', async ({ page }) => {
  await page.goto(`/newsletter/${FEATURED_NEWSLETTER.id}`);
  await expectSiteHeaderAndFooter(page);
});

// The archived newsletter body (raw_html) may contain its own <h1> elements, as the
// seeded one does, so the assertion covers every h1 the site itself renders, i.e. those outside that body.
test('newsletter detail page renders exactly one site h1 and it is the subject', async ({ page }) => {
  await page.goto(`/newsletter/${FEATURED_NEWSLETTER.id}`);
  const siteHeadings = page.locator('h1:not([data-testid="newsletter-detail-content"] h1)');
  await expect(siteHeadings).toHaveCount(1);
  await expect(siteHeadings).toHaveText(FEATURED_NEWSLETTER.subject);
  await expect(page.getByRole('main').getByTestId('newsletter-detail-title')).toHaveText(FEATURED_NEWSLETTER.subject);
});

test.describe('on a phone', () => {
  test.use({ viewport: { width: 375, height: 800 } });

  test('keeps the header compact: one-line site name, no tagline', async ({ page }) => {
    await page.goto('/search');
    const header = page.getByRole('banner');

    await expect(header.getByTestId('site-tagline')).toBeHidden();
    const nameBox = await header.getByTestId('site-name').boundingBox();
    expect(nameBox?.height).toBeLessThan(30);
    const headerBox = await header.boundingBox();
    expect(headerBox?.height).toBeLessThan(160);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  });
});
