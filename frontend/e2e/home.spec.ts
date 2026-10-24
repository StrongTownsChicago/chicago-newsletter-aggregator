import { test, expect } from '@playwright/test';
import { FEATURED_NEWSLETTER, HOME_PAGE_TWO, NEWSLETTER_COUNT, NO_SUMMARY_NEWSLETTER } from './fixtures/db/facts';

const PAGE_SIZE = 20;

test('has title', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveTitle(/Chicago Alderman Newsletter Tracker/);
});

test('has main heading', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Chicago Alderman Newsletter Tracker', level: 1 })).toBeVisible();
});

test('lists the newest newsletters first with their source, ward and topics', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByTestId('newsletter-count')).toContainText(`Browse ${NEWSLETTER_COUNT} newsletters`);
  const cards = page.getByTestId('newsletter-card');
  await expect(cards).toHaveCount(PAGE_SIZE);

  const newest = cards.first();
  await expect(newest.getByTestId('newsletter-title')).toHaveText(FEATURED_NEWSLETTER.subject);
  await expect(newest.getByTestId('newsletter-source')).toHaveText(FEATURED_NEWSLETTER.sourceName);
  await expect(newest.getByTestId('newsletter-ward-link')).toHaveText(`Ward ${FEATURED_NEWSLETTER.ward}`);
  await expect(newest.locator('time')).toHaveText(FEATURED_NEWSLETTER.receivedDate);
  for (const label of FEATURED_NEWSLETTER.topicLabels) {
    await expect(newest.getByText(label, { exact: true })).toBeVisible();
  }
});

test('paginates to the older newsletters', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('pagination')).toBeVisible();
  await page.getByTestId('pagination-next').click();

  await expect(page).toHaveURL(/\/\?page=2$/);
  const cards = page.getByTestId('newsletter-card');
  await expect(cards).toHaveCount(HOME_PAGE_TWO.count);
  await expect(cards.first().getByTestId('newsletter-title')).toHaveText(HOME_PAGE_TWO.firstSubject);
  await expect(page.getByTestId('pagination-next')).toHaveCount(0);
});

test('a page past the end says so', async ({ page }) => {
  await page.goto('/?page=3');
  await expect(page.getByTestId('newsletters-page-empty')).toBeVisible();
});

test('can toggle newsletter summary expansion', async ({ page }) => {
  await page.goto('/');
  const card = page.getByTestId('newsletter-card').first();
  const toggle = card.getByTestId('summary-toggle');
  const summary = card.getByTestId('newsletter-summary');

  await expect(summary).toHaveClass(/line-clamp-2/);
  await expect(toggle).toHaveText('Show more');

  await toggle.click();

  await expect(summary).not.toHaveClass(/line-clamp-2/);
  await expect(toggle).toHaveText('Show less');
});

test('a newsletter without a summary shows no summary block', async ({ page }) => {
  await page.goto('/');
  const card = page.getByTestId('newsletter-card').filter({ hasText: NO_SUMMARY_NEWSLETTER.subject });
  await expect(card).toHaveCount(1);
  await expect(card.getByTestId('newsletter-summary')).toHaveCount(0);
  await expect(card.getByTestId('summary-toggle')).toHaveCount(0);
});
