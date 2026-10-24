// Automated WCAG 2.1 A/AA checks (axe-core) on every page, populated from the
// local database's seed, at desktop and phone widths.
import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page } from '@playwright/test';
import monthlyReports from '../src/generated/monthly-reports.json' with { type: 'json' };
import { FEATURED_NEWSLETTER, READER_RULES, RULES_READER, SEARCH_WORD, WARD_40, type SeedUser } from './fixtures/db/facts';
import { signIn } from './support/auth';
import { useOfflineFixtures } from './offline-guard';

const WCAG_AA_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

const reportMonth = monthlyReports.reports[0]?.month;

interface ScannedPage {
  name: string;
  path: string;
  /** Signed in as this user before the page is opened. */
  user?: SeedUser;
  /** Brings the page into the state to scan once it has loaded. */
  prepare?: (page: Page) => Promise<void>;
}

const SCANNED_PAGES: ScannedPage[] = [
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

const VIEWPORTS = [
  { name: 'desktop', size: { width: 1280, height: 900 } },
  { name: 'phone', size: { width: 375, height: 800 } },
];

useOfflineFixtures();

/** One line per violation: rule, impact, and the first few offending selectors. */
const summarizeViolations = (violations: { id: string; impact?: string | null; nodes: { target: unknown[] }[] }[]) =>
  violations.map(
    ({ id, impact, nodes }) =>
      `${id} (${impact ?? 'unknown'}): ${nodes
        .slice(0, 3)
        .map((node) => node.target.join(' '))
        .join(', ')}${nodes.length > 3 ? ` and ${nodes.length - 3} more` : ''}`,
  );

for (const viewport of VIEWPORTS) {
  test.describe(`${viewport.name} accessibility`, () => {
    test.use({ viewport: viewport.size });

    for (const { name, path, user, prepare } of SCANNED_PAGES) {
      test(`${name} has no WCAG A/AA violations`, async ({ page }) => {
        if (user) await signIn(page, user);
        await page.goto(path);
        // A redirect (e.g. sign-in pages with notifications off) would scan the wrong page.
        expect(new URL(page.url()).pathname).toBe(new URL(path, page.url()).pathname);
        await prepare?.(page);

        const { violations } = await new AxeBuilder({ page }).withTags(WCAG_AA_TAGS).analyze();

        expect(summarizeViolations(violations)).toEqual([]);
      });
    }
  });
}
