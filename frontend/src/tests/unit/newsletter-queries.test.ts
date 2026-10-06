import { describe, it, expect } from 'vitest';
import {
  buildNewsletterCardSelect,
  buildNewsletterCountSelect,
  NEWSLETTER_DETAIL_SELECT,
} from '../../lib/newsletter-queries';

/** Split a PostgREST select string into top-level columns and the sources embed. */
const parseSelect = (select: string) => {
  const embedMatch = select.match(/(sources(?:!inner)?)\(([^)]*)\)/);
  const topLevel = select
    .replace(/sources(?:!inner)?\([^)]*\)/, '')
    .split(',')
    .map((column) => column.trim())
    .filter(Boolean);
  const embedColumns = embedMatch
    ? embedMatch[2].split(',').map((column) => column.trim()).filter(Boolean)
    : [];
  return { topLevel, relation: embedMatch?.[1] ?? null, embedColumns };
};

// Every field NewsletterCard.astro reads from its `newsletter` prop.
const CARD_NEWSLETTER_FIELDS = ['id', 'subject', 'received_date', 'summary', 'topics', 'relevance_score'];
const CARD_SOURCE_FIELDS = ['name', 'ward_number'];

const NEWSLETTER_BODY_FIELDS = ['raw_html', 'plain_text'];
const SOURCE_CONTACT_FIELDS = ['email_address', 'phone'];

describe('buildNewsletterCardSelect', () => {
  describe.each([false, true])('filtersOnSource=%s', (filtersOnSource) => {
    const { topLevel, embedColumns } = parseSelect(buildNewsletterCardSelect({ filtersOnSource }));

    it('includes every newsletter field NewsletterCard renders', () => {
      expect(topLevel).toEqual(expect.arrayContaining(CARD_NEWSLETTER_FIELDS));
    });

    it('includes every source field NewsletterCard renders', () => {
      expect(embedColumns).toEqual(expect.arrayContaining(CARD_SOURCE_FIELDS));
    });

    it('never selects all columns', () => {
      expect(topLevel).not.toContain('*');
      expect(embedColumns).not.toContain('*');
    });

    it('excludes newsletter bodies', () => {
      for (const field of NEWSLETTER_BODY_FIELDS) {
        expect(topLevel).not.toContain(field);
      }
    });

    it('excludes source contact details', () => {
      for (const field of SOURCE_CONTACT_FIELDS) {
        expect(embedColumns).not.toContain(field);
      }
    });
  });

  it('uses a left join when not filtering on sources', () => {
    expect(parseSelect(buildNewsletterCardSelect({ filtersOnSource: false })).relation).toBe('sources');
  });

  it('uses an inner join when filtering on sources so filters restrict rows', () => {
    expect(parseSelect(buildNewsletterCardSelect({ filtersOnSource: true })).relation).toBe('sources!inner');
  });
});

describe('buildNewsletterCountSelect', () => {
  it('selects only the id when not filtering on sources', () => {
    expect(buildNewsletterCountSelect({ filtersOnSource: false })).toBe('id');
  });

  it('keeps the inner join when filtering on sources so counts match the listing', () => {
    const { topLevel, relation, embedColumns } = parseSelect(
      buildNewsletterCountSelect({ filtersOnSource: true }),
    );
    expect(topLevel).toEqual(['id']);
    expect(relation).toBe('sources!inner');
    expect(embedColumns).toEqual(['id']);
  });
});

describe('NEWSLETTER_DETAIL_SELECT', () => {
  const { topLevel, relation, embedColumns } = parseSelect(NEWSLETTER_DETAIL_SELECT);

  it('selects all newsletter columns because the detail page renders raw_html', () => {
    expect(topLevel).toEqual(['*']);
  });

  it('embeds only the source fields the detail page renders', () => {
    expect(relation).toBe('sources');
    expect(embedColumns.sort()).toEqual(['email_address', 'name', 'phone', 'ward_number']);
  });
});
