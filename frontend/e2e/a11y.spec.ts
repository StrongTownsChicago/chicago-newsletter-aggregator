// Automated WCAG 2.1 A/AA checks (axe-core) on the pages that render without
// the database. Run with `npm run test:e2e:analytics`: its dev server has
// placeholder Supabase settings, so database-backed pages render their
// load-failure state, which still covers the shared header, nav, forms and footer.
import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page } from '@playwright/test';
import monthlyReports from '../src/generated/monthly-reports.json' with { type: 'json' };
import { useOfflineFixtures } from './offline-guard';

const WCAG_AA_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

const reportMonth = monthlyReports.reports[0]?.month;

interface ScannedPage {
  name: string;
  path: string;
  /** Brings the page into the state to scan once it has loaded. */
  prepare?: (page: Page) => Promise<void>;
}

const SCANNED_PAGES: ScannedPage[] = [
  { name: 'home', path: '/' },
  {
    name: 'search with filters open',
    path: '/search?q=zoning&ward=1&topic=bike_lanes',
    prepare: (page) => page.getByTestId('search-filters-toggle').click(),
  },
  { name: 'ward directory', path: '/wards' },
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

    for (const { name, path, prepare } of SCANNED_PAGES) {
      test(`${name} has no WCAG A/AA violations`, async ({ page }) => {
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
