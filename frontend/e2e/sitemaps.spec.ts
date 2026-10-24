import { test, expect } from '@playwright/test';
import { ALL_NEWSLETTER_IDS } from './fixtures/db/facts';

const SITE_URL = 'https://chicago-newsletter-aggregator.open-advocacy.com';

const listedLocations = (xml: string): string[] =>
  [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map(([, location]) => location);

test('the newsletter sitemap lists every newsletter', async ({ request }) => {
  const response = await request.get('/sitemap-newsletters.xml');

  expect(response.status()).toBe(200);
  expect(response.headers()['content-type']).toContain('application/xml');
  expect(listedLocations(await response.text()).sort()).toEqual(
    ALL_NEWSLETTER_IDS.map((id) => `${SITE_URL}/newsletter/${id}`).sort(),
  );
});

test('the ward sitemap lists every ward', async ({ request }) => {
  const response = await request.get('/sitemap-wards.xml');

  expect(response.status()).toBe(200);
  expect(listedLocations(await response.text())).toEqual(
    Array.from({ length: 50 }, (_, index) => `${SITE_URL}/ward/${index + 1}`),
  );
});
