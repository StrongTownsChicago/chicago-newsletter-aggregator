import { test, expect, type Page } from '@playwright/test';

async function expectSiteHeaderAndFooter(page: Page) {
  const header = page.getByRole('banner');
  await expect(header).toBeVisible();
  await expect(header.getByTestId('site-name')).toHaveAttribute('href', '/');
  await expect(header.getByTestId('site-tagline')).toBeVisible();
  await expect(header.locator('h1')).toHaveCount(0);
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
    'https://github.com/matt-hendrick/chicago-newsletter-aggregator',
  );
}

async function openFirstNewsletter(page: Page): Promise<string | null> {
  await page.goto('/');
  const firstCardTitle = page.getByTestId('newsletter-title').first();
  if ((await firstCardTitle.count()) === 0) {
    return null;
  }
  const subject = await firstCardTitle.innerText();
  await firstCardTitle.locator('a').click();
  await expect(page).toHaveURL(/\/newsletter\/.+/);
  return subject;
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
    await expect(page.getByRole('main').locator('h1')).toHaveCount(1);
  });
}

test('renders the site header and footer on a newsletter detail page', async ({ page }) => {
  const subject = await openFirstNewsletter(page);
  test.skip(subject === null, 'No newsletters to open');
  await expectSiteHeaderAndFooter(page);
});

// The archived newsletter body (raw_html) may contain its own <h1> elements, so the
// assertion covers every h1 the site itself renders, i.e. those outside that body.
test('newsletter detail page renders exactly one site h1 and it is the subject', async ({ page }) => {
  const subject = await openFirstNewsletter(page);
  test.skip(subject === null, 'No newsletters to open');
  const siteHeadings = page.locator('h1:not([data-testid="newsletter-detail-content"] h1)');
  await expect(siteHeadings).toHaveCount(1);
  await expect(siteHeadings).toHaveText(subject ?? '');
  await expect(page.getByRole('main').getByTestId('newsletter-detail-title')).toHaveText(subject ?? '');
});
