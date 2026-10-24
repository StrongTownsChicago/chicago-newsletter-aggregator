// Automated WCAG 2.1 A/AA checks (axe-core) on every page, populated from the
// local database's seed, at desktop and phone widths.
import AxeBuilder from '@axe-core/playwright';
import { test, expect } from '@playwright/test';
import { signIn } from './support/auth';
import { SCANNED_PAGES } from './support/scanned-pages';
import { useOfflineFixtures } from './offline-guard';

const WCAG_AA_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

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
