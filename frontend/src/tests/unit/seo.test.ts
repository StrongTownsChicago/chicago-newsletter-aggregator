import { describe, it, expect } from 'vitest';
import {
  META_DESCRIPTION_MAX_LENGTH,
  buildCanonicalUrl,
  buildNewsletterDescription,
  buildWardDescription,
  buildWardStructuredData,
  buildWardTitle,
  formatShortReceivedDate,
  isNonProductionHost,
  serializeJsonLd,
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

  it('drops the .html of prerendered output files', () => {
    expect(buildCanonicalUrl('/reports/2026-09.html', SITE)).toBe(`${SITE}/reports/2026-09`);
    expect(buildCanonicalUrl('/reports.html', SITE)).toBe(`${SITE}/reports`);
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

describe('buildWardTitle', () => {
  it('leads with the ordinal ward and the alderman', () => {
    expect(buildWardTitle(38, ['Nicholas Sposato'])).toBe(
      '38th Ward Alderman Nicholas Sposato: Newsletters & Updates',
    );
  });

  it('names every alderman when a ward has several', () => {
    expect(buildWardTitle(1, ['Ann Lee', 'Bo Park'])).toBe(
      '1st Ward Aldermen Ann Lee and Bo Park: Newsletters & Updates',
    );
  });

  it('describes the ward when no alderman is on file', () => {
    expect(buildWardTitle(12, [])).toBe('12th Ward, Chicago: Alderman Newsletters & Updates');
  });
});

describe('formatShortReceivedDate', () => {
  it('uses the Chicago calendar day', () => {
    // 03:00 UTC on Oct 23 is still Oct 22 in Chicago.
    expect(formatShortReceivedDate('2026-10-23T03:00:00Z')).toBe('Oct 22');
  });

  it('returns null for an invalid date', () => {
    expect(formatShortReceivedDate('not a date')).toBeNull();
  });
});

describe('buildWardDescription', () => {
  const latest = { subject: 'Leaf collection starts Monday', received_date: '2026-10-22T15:00:00Z' };

  it('leads with what the alderman told the ward and the latest newsletter', () => {
    expect(buildWardDescription(38, ['Nicholas Sposato'], latest)).toBe(
      'What Ald. Nicholas Sposato told 38th Ward residents. Latest (Oct 22): Leaf collection starts Monday',
    );
  });

  it('names several aldermen together', () => {
    expect(buildWardDescription(2, ['Ann Lee', 'Bo Park'], latest)).toBe(
      'What the 2nd Ward aldermen, Ann Lee and Bo Park, told residents. Latest (Oct 22): Leaf collection starts Monday',
    );
  });

  it('caps long subjects at the meta description length', () => {
    const description = buildWardDescription(38, ['Nicholas Sposato'], {
      ...latest,
      subject: 'word '.repeat(60),
    });
    expect(description.length).toBeLessThanOrEqual(META_DESCRIPTION_MAX_LENGTH);
    expect(description.endsWith('…')).toBe(true);
  });

  it('falls back to the page summary without a latest newsletter', () => {
    expect(buildWardDescription(49, ['Maria Hadden'], null)).toBe(
      "Read newsletters from Maria Hadden, alderman for Chicago's 49th Ward, along with ward office contact information.",
    );
  });

  it('falls back when the latest subject is blank', () => {
    expect(buildWardDescription(49, ['Maria Hadden'], { ...latest, subject: '  ' })).toContain(
      'Read newsletters from Maria Hadden',
    );
  });

  it('falls back to a generic sender when no alderman is on file', () => {
    expect(buildWardDescription(12, [], null)).toContain("the alderman for Chicago's 12th Ward");
  });
});

describe('buildWardStructuredData', () => {
  const source = {
    name: 'Nicholas Sposato',
    website: 'https://www.38thward.com',
    phone: '(773) 555-0138',
    email_address: 'ward38@cityofchicago.org',
  };

  it('describes the breadcrumb path to the ward page', () => {
    const [breadcrumbs] = buildWardStructuredData(38, [source], SITE)['@graph'] as unknown[];
    expect(breadcrumbs).toEqual({
      '@type': 'BreadcrumbList',
      itemListElement: [
        { '@type': 'ListItem', position: 1, name: 'Home', item: `${SITE}/` },
        { '@type': 'ListItem', position: 2, name: 'Wards', item: `${SITE}/wards` },
        { '@type': 'ListItem', position: 3, name: '38th Ward', item: `${SITE}/ward/38` },
      ],
    });
  });

  it('describes each alderman with their public contact details', () => {
    const [, person] = buildWardStructuredData(38, [source], SITE)['@graph'] as unknown[];
    expect(person).toEqual({
      '@type': 'Person',
      name: 'Nicholas Sposato',
      jobTitle: 'Alderman, 38th Ward',
      worksFor: { '@type': 'GovernmentOrganization', name: 'Chicago City Council' },
      telephone: '(773) 555-0138',
      email: 'ward38@cityofchicago.org',
      url: 'https://www.38thward.com',
    });
  });

  it('omits missing or unsafe contact details', () => {
    const unsafeSource = { name: 'A', website: 'javascript:alert(1)', phone: null, email_address: ' ' };
    const [, person] = buildWardStructuredData(5, [unsafeSource], SITE)['@graph'] as unknown[];
    expect(person).toEqual({
      '@type': 'Person',
      name: 'A',
      jobTitle: 'Alderman, 5th Ward',
      worksFor: { '@type': 'GovernmentOrganization', name: 'Chicago City Council' },
    });
  });

  it('lists only the breadcrumbs when no alderman is on file', () => {
    expect(buildWardStructuredData(5, [], SITE)['@graph']).toHaveLength(1);
  });
});

describe('serializeJsonLd', () => {
  it('escapes "<" so stored text cannot close the script tag', () => {
    const name = '</script><script>alert(1)</script>';
    const json = serializeJsonLd({ name });
    expect(json).not.toContain('<');
    expect(JSON.parse(json)).toEqual({ name });
  });
});
