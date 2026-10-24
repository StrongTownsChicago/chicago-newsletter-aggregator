// The pages the accessibility and Content-Security-Policy specs open, populated
// from the local database's seed, with the state each is checked in.
import { expect, type Page } from '@playwright/test';
import monthlyReports from '../../src/generated/monthly-reports.json' with { type: 'json' };
import { FEATURED_NEWSLETTER, READER_RULES, RULES_READER, SEARCH_WORD, WARD_40, type SeedUser } from '../fixtures/db/facts';

const reportMonth = monthlyReports.reports[0]?.month;

export interface ScannedPage {
  name: string;
  path: string;
  /** Signed in as this user before the page is opened. */
  user?: SeedUser;
  /** Brings the page into the state to scan once it has loaded. */
  prepare?: (page: Page) => Promise<void>;
}

export const SCANNED_PAGES: ScannedPage[] = [
  { name: 'home', path: '/' },
  {
    name: 'search results with the timeline',
    path: `/search?q=${SEARCH_WORD}`,
    prepare: (page) => expect(page.getByTestId('search-timeline').getByRole('link').first()).toBeVisible(),
  },
  {
    name: 'search with filters open',
    path: `/search?q=${SEARCH_WORD}&ward=1&topic=bike_lanes`,
    prepare: (page) => page.getByTestId('search-filters-toggle').click(),
  },
  { name: 'ward directory', path: '/wards' },
  { name: 'ward page', path: `/ward/${WARD_40.ward}` },
  { name: 'newsletter', path: `/newsletter/${FEATURED_NEWSLETTER.id}` },
  { name: 'preferences', path: '/preferences', user: RULES_READER },
  {
    name: 'preferences with the rule modal open',
    path: '/preferences',
    user: RULES_READER,
    prepare: async (page) => {
      await page.getByTestId('notification-rule').filter({ hasText: READER_RULES[0].name }).getByRole('button', { name: 'Edit' }).click();
      await expect(page.locator('#ruleModal')).toBeVisible();
    },
  },
  {
    name: 'analytics',
    path: '/analytics',
    // Export buttons are enabled last in a dashboard render, so the charts and controls exist.
    prepare: (page) => expect(page.getByRole('button', { name: 'Download PNG of Civic calendar' })).toBeEnabled(),
  },
  { name: 'reports index', path: '/reports' },
  ...(reportMonth ? [{ name: 'monthly report', path: `/reports/${reportMonth}` }] : []),
  { name: 'login', path: '/login' },
  { name: 'signup', path: '/signup' },
  { name: 'unsubscribe without a token', path: '/unsubscribe' },
  { name: 'not found', path: '/no-such-page' },
];
