import { describe, it, expect } from 'vitest';
import {
  META_DESCRIPTION_MAX_LENGTH,
  buildCanonicalUrl,
  buildNewsletterDescription,
  isNonProductionHost,
  truncateDescription,
} from '../../lib/seo';

const SITE = 'https://chicago-newsletter-aggregator.open-advocacy.com';

describe('truncateDescription', () => {
  it('returns short text unchanged apart from whitespace normalization', () => {
    expect(truncateDescription('  Ward 1\n\nupdates  ')).toBe('Ward 1 updates');
  });

  it('keeps text exactly at the limit', () => {
    const text = 'a'.repeat(META_DESCRIPTION_MAX_LENGTH);
    expect(truncateDescription(text)).toBe(text);
  });

  it('cuts long text at a word boundary and appends an ellipsis', () => {
    const text = 'Zoning hearing scheduled. '.repeat(20);
    const result = truncateDescription(text);

    expect(result.length).toBeLessThanOrEqual(META_DESCRIPTION_MAX_LENGTH);
    expect(result.endsWith('…')).toBe(true);
    expect(result).not.toMatch(/[\s.]…$/);
    expect(text.startsWith(result.slice(0, -1))).toBe(true);
  });

  it('hard-cuts a single word longer than the limit', () => {
    const result = truncateDescription('x'.repeat(200), 20);
    expect(result).toBe(`${'x'.repeat(19)}…`);
  });
});

describe('buildNewsletterDescription', () => {
  const baseNewsletter = {
    subject: 'Weekly Ward Update',
    summary: null,
    received_date: '2026-03-15T15:00:00Z',
    sources: { name: 'Alderman Jane Doe', ward_number: '32' },
  };

  it('uses the LLM summary when present', () => {
    const description = buildNewsletterDescription({
      ...baseNewsletter,
      summary: 'Updates on the new bike lane and a community meeting.',
    });
    expect(description).toBe('Updates on the new bike lane and a community meeting.');
  });

  it('truncates long summaries', () => {
    const description = buildNewsletterDescription({
      ...baseNewsletter,
      summary: 'The alderman discusses transit. '.repeat(20),
    });
    expect(description.length).toBeLessThanOrEqual(META_DESCRIPTION_MAX_LENGTH);
    expect(description.endsWith('…')).toBe(true);
  });

  it('falls back to sender, ward, date, and subject when summary is null', () => {
    expect(buildNewsletterDescription(baseNewsletter)).toBe(
      'Newsletter from Alderman Jane Doe (Ward 32) sent March 15, 2026: Weekly Ward Update',
    );
  });

  it('treats a whitespace-only summary as missing', () => {
    expect(buildNewsletterDescription({ ...baseNewsletter, summary: '   ' })).toMatch(
      /^Newsletter from Alderman Jane Doe/,
    );
  });

  it('omits the ward when the source has none', () => {
    const description = buildNewsletterDescription({
      ...baseNewsletter,
      sources: { name: 'Mayor’s Office', ward_number: null },
    });
    expect(description).toBe('Newsletter from Mayor’s Office sent March 15, 2026: Weekly Ward Update');
  });

  it('uses a generic sender and omits an invalid date', () => {
    const description = buildNewsletterDescription({
      ...baseNewsletter,
      received_date: 'not a date',
      sources: null,
    });
    expect(description).toBe('Newsletter from a Chicago alderman: Weekly Ward Update');
  });
});

describe('buildCanonicalUrl', () => {
  it('resolves the root path', () => {
    expect(buildCanonicalUrl('/', SITE)).toBe(`${SITE}/`);
  });

  it('strips trailing slashes from non-root paths', () => {
    expect(buildCanonicalUrl('/search/', SITE)).toBe(`${SITE}/search`);
  });

  it('keeps newsletter detail paths', () => {
    expect(buildCanonicalUrl('/newsletter/abc-123', new URL(SITE))).toBe(
      `${SITE}/newsletter/abc-123`,
    );
  });

  it('keeps the page number for page 2 and beyond of a paginated listing', () => {
    expect(buildCanonicalUrl('/', SITE, 3)).toBe(`${SITE}/?page=3`);
  });

  it('omits the page number for the first page', () => {
    expect(buildCanonicalUrl('/', SITE, 1)).toBe(`${SITE}/`);
  });

  it('omits invalid page numbers', () => {
    expect(buildCanonicalUrl('/', SITE, Number.NaN)).toBe(`${SITE}/`);
    expect(buildCanonicalUrl('/', SITE, -2)).toBe(`${SITE}/`);
    expect(buildCanonicalUrl('/', SITE, 2.5)).toBe(`${SITE}/`);
  });
});

describe('isNonProductionHost', () => {
  it('returns false for the production host', () => {
    expect(isNonProductionHost('chicago-newsletter-aggregator.open-advocacy.com', SITE)).toBe(false);
  });

  it('compares hosts case-insensitively', () => {
    expect(isNonProductionHost('Chicago-Newsletter-Aggregator.Open-Advocacy.com', new URL(SITE))).toBe(false);
  });

  it.each([
    ['pages.dev production alias', 'chicago-newsletter-aggregator.pages.dev'],
    ['preview deployment', 'abc123.chicago-newsletter-aggregator.pages.dev'],
    ['local dev server', 'localhost:4321'],
    ['parent domain', 'open-advocacy.com'],
  ])('returns true for %s', (_label, host) => {
    expect(isNonProductionHost(host, SITE)).toBe(true);
  });

  it('returns true when no production site is configured', () => {
    expect(isNonProductionHost('chicago-newsletter-aggregator.open-advocacy.com', undefined)).toBe(true);
  });
});
