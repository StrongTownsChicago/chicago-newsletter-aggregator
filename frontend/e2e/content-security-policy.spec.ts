// The Content-Security-Policy blocks nothing the site needs on any page, and
// blocks script that stored newsletter HTML carries. This runs on the dev
// server: it never inlines scripts or loads Cloudflare's beacon, and serves
// prerendered pages through the middleware rather than public/_headers.
import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { test, expect, type Page } from '@playwright/test';
import { CONTENT_SECURITY_POLICY, CONTENT_SECURITY_POLICY_HEADER } from '../src/lib/content-security-policy';
import { UNSAFE_MARKUP_NEWSLETTER } from './fixtures/db/facts';
import { signIn } from './support/auth';
import { SCANNED_PAGES } from './support/scanned-pages';
import { useOfflineFixtures } from './offline-guard';

useOfflineFixtures();

/** Records every policy violation on the page's documents, from before any page script runs. */
async function recordViolations(page: Page): Promise<() => Promise<string[]>> {
  await page.addInitScript(() => {
    const violations: string[] = [];
    Object.assign(window, { cspViolations: violations });
    document.addEventListener('securitypolicyviolation', (event) => {
      violations.push(`${event.effectiveDirective} blocked ${event.blockedURI} (${event.sourceFile}:${event.lineNumber}) ${event.sample}`);
    });
  });
  return () => page.evaluate(() => (window as unknown as { cspViolations: string[] }).cspViolations);
}

for (const { name, path, user, prepare } of SCANNED_PAGES) {
  test(`${name} runs under the policy without violations`, async ({ page }) => {
    if (user) await signIn(page, user);
    const readViolations = await recordViolations(page);

    const response = await page.goto(path);
    await prepare?.(page);

    expect(response?.headers()[CONTENT_SECURITY_POLICY_HEADER.toLowerCase()]).toBe(CONTENT_SECURITY_POLICY);
    expect(await readViolations()).toEqual([]);
  });
}

/** Serves a page framing `frameUrl` from its own loopback port: another origin to the dev server. */
async function startEmbeddingSite(frameUrl: string): Promise<{ server: Server; url: string }> {
  const server = createServer((_request, response) => {
    response.writeHead(200, { 'Content-Type': 'text/html' });
    response.end(`<!doctype html><iframe src="${frameUrl}" title="Embedded site"></iframe>`);
  });
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  return { server, url: `http://127.0.0.1:${(server.address() as AddressInfo).port}/` };
}

// The embedding page comes from a real server, not page.route: Chrome treats a
// fulfilled response as a public site and blocks its frames to loopback addresses.
test('another site can embed a page in a frame', async ({ page, baseURL }) => {
  const embeddingSite = await startEmbeddingSite(`${baseURL}/`);
  try {
    await page.route(embeddingSite.url, (route) => route.continue());

    await page.goto(embeddingSite.url);

    await expect(page.frameLocator('iframe').getByRole('heading', { level: 1 })).toBeVisible();
  } finally {
    embeddingSite.server.close();
  }
});

test('script in stored newsletter HTML does not run', async ({ page }) => {
  const readViolations = await recordViolations(page);

  await page.goto(`/newsletter/${UNSAFE_MARKUP_NEWSLETTER.id}`);
  await expect(page.getByRole('heading', { level: 1, name: UNSAFE_MARKUP_NEWSLETTER.subject })).toBeVisible();

  await expect.poll(readViolations).toHaveLength(2);
  expect(await page.locator('html').getAttribute('data-unsafe-markup-ran')).toBeNull();
});
