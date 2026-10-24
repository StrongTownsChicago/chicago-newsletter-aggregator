import { test, expect } from '@playwright/test';
import {
  AGENCY_NEWSLETTER,
  FEATURED_NEWSLETTER,
  LONG_SUBJECT_NEWSLETTER,
  NO_SUMMARY_NEWSLETTER,
  PLAIN_TEXT_NEWSLETTER,
} from './fixtures/db/facts';

test('opens a newsletter from its card', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('newsletter-title').first().getByRole('link').click();

  await expect(page).toHaveURL(`/newsletter/${FEATURED_NEWSLETTER.id}`);
  await expect(page.getByTestId('newsletter-detail-title')).toHaveText(FEATURED_NEWSLETTER.subject);
});

test('shows the subject, source, date, topics, summary and body', async ({ page }) => {
  await page.goto(`/newsletter/${FEATURED_NEWSLETTER.id}`);

  await expect(page).toHaveTitle(`${FEATURED_NEWSLETTER.subject} - Chicago Alderman Newsletter Tracker`);
  const detail = page.getByTestId('newsletter-detail');
  await expect(detail.getByTestId('newsletter-detail-source')).toHaveText(FEATURED_NEWSLETTER.sourceName);
  await expect(detail.getByTestId('newsletter-detail-ward-link')).toHaveAttribute('href', `/ward/${FEATURED_NEWSLETTER.ward}`);
  await expect(detail.locator('time')).toHaveText(FEATURED_NEWSLETTER.receivedDate);
  await expect(detail.getByRole('link', { name: FEATURED_NEWSLETTER.sourcePhone })).toHaveAttribute(
    'href',
    `tel:${FEATURED_NEWSLETTER.sourcePhone}`,
  );
  await expect(detail.getByRole('link', { name: FEATURED_NEWSLETTER.sourceEmail })).toHaveAttribute(
    'href',
    `mailto:${FEATURED_NEWSLETTER.sourceEmail}`,
  );
  for (const label of FEATURED_NEWSLETTER.topicLabels) {
    await expect(detail.getByText(label, { exact: true })).toBeVisible();
  }
  await expect(detail.getByText('Summary', { exact: true })).toBeVisible();

  const body = page.getByTestId('newsletter-detail-content');
  await expect(body.getByRole('heading', { name: FEATURED_NEWSLETTER.bodyHeading, level: 1 })).toBeVisible();
  await expect(body.getByRole('table')).toBeVisible();
  await expect(body.getByRole('img')).toBeVisible();
  await expect(body.getByRole('link', { name: FEATURED_NEWSLETTER.bodyLink.name })).toHaveAttribute(
    'href',
    FEATURED_NEWSLETTER.bodyLink.href,
  );
});

test('shows the plain text when a newsletter has no HTML body', async ({ page }) => {
  await page.goto(`/newsletter/${PLAIN_TEXT_NEWSLETTER.id}`);

  const body = page.getByTestId('newsletter-detail-content');
  for (const line of PLAIN_TEXT_NEWSLETTER.bodyLines) {
    await expect(body).toContainText(line);
  }
  await expect(body.locator('p')).toHaveCount(0);
});

test('leaves out the summary block when there is no summary', async ({ page }) => {
  await page.goto(`/newsletter/${NO_SUMMARY_NEWSLETTER.id}`);

  await expect(page.getByTestId('newsletter-detail-title')).toHaveText(NO_SUMMARY_NEWSLETTER.subject);
  await expect(page.getByTestId('newsletter-detail').getByText('Summary', { exact: true })).toHaveCount(0);
});

test('wraps a long subject without widening the page on a phone', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto(`/newsletter/${LONG_SUBJECT_NEWSLETTER.id}`);

  await expect(page.getByTestId('newsletter-detail-title')).toHaveText(LONG_SUBJECT_NEWSLETTER.subject);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
});

test('a newsletter from a source without a ward has no ward link', async ({ page }) => {
  await page.goto(`/newsletter/${AGENCY_NEWSLETTER.id}`);

  await expect(page.getByTestId('newsletter-detail-source')).toHaveText(AGENCY_NEWSLETTER.sourceName);
  await expect(page.getByTestId('newsletter-detail-ward-link')).toHaveCount(0);
});

test('can return home from detail page via the site header', async ({ page }) => {
  await page.goto(`/newsletter/${FEATURED_NEWSLETTER.id}`);
  await page.getByTestId('site-name').click();
  await expect(page).toHaveURL(/\/$/);
});
