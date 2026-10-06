import { describe, it, expect, vi } from 'vitest';
import type { SupabaseClient } from '@supabase/supabase-js';
import {
  buildNewsletterSitemapXml,
  fetchNewsletterSitemapEntries,
  type NewsletterSitemapEntry,
} from '../../lib/sitemap';

const SITE = 'https://chicago-newsletter-aggregator.open-advocacy.com';

describe('buildNewsletterSitemapXml', () => {
  it('emits one url element per newsletter with an ISO lastmod', () => {
    const xml = buildNewsletterSitemapXml(
      [
        { id: 'aaa', received_date: '2026-03-15T15:00:00+00:00' },
        { id: 'bbb', received_date: '2026-03-16' },
      ],
      SITE,
    );

    expect(xml).toBe(
      [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        `<url><loc>${SITE}/newsletter/aaa</loc><lastmod>2026-03-15T15:00:00.000Z</lastmod></url>`,
        `<url><loc>${SITE}/newsletter/bbb</loc><lastmod>2026-03-16T00:00:00.000Z</lastmod></url>`,
        '</urlset>',
      ].join('\n'),
    );
  });

  it('omits lastmod when received_date is missing or invalid', () => {
    const xml = buildNewsletterSitemapXml(
      [
        { id: 'aaa', received_date: null },
        { id: 'bbb', received_date: 'garbage' },
      ],
      SITE,
    );
    expect(xml).not.toContain('<lastmod>');
    expect(xml.match(/<url>/g)).toHaveLength(2);
  });

  it('encodes and escapes ids in loc', () => {
    const xml = buildNewsletterSitemapXml([{ id: 'a&b<c', received_date: null }], SITE);
    expect(xml).toContain(`<loc>${SITE}/newsletter/a%26b%3Cc</loc>`);
  });

  it('produces a valid empty urlset', () => {
    const xml = buildNewsletterSitemapXml([], new URL(SITE));
    expect(xml).toBe(
      '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n</urlset>',
    );
  });
});

const createPagedSupabase = (pages: Array<{ data: NewsletterSitemapEntry[] | null; error: { message: string } | null }>) => {
  const range = vi.fn();
  pages.forEach((page) => range.mockResolvedValueOnce(page));
  const query = {
    select: vi.fn().mockReturnThis(),
    order: vi.fn().mockReturnThis(),
    range,
  };
  const supabase = { from: vi.fn(() => query) } as unknown as SupabaseClient;
  return { supabase, query };
};

const makeEntries = (count: number, offset = 0): NewsletterSitemapEntry[] =>
  Array.from({ length: count }, (_, index) => ({
    id: `id-${offset + index}`,
    received_date: '2026-01-01T00:00:00Z',
  }));

describe('fetchNewsletterSitemapEntries', () => {
  it('pages through results until a short page is returned', async () => {
    const { supabase, query } = createPagedSupabase([
      { data: makeEntries(2, 0), error: null },
      { data: makeEntries(2, 2), error: null },
      { data: makeEntries(1, 4), error: null },
    ]);

    const entries = await fetchNewsletterSitemapEntries(supabase, 2);

    expect(entries.map((entry) => entry.id)).toEqual(['id-0', 'id-1', 'id-2', 'id-3', 'id-4']);
    expect(query.select).toHaveBeenCalledWith('id, received_date');
    expect(query.order).toHaveBeenCalledWith('id', { ascending: true });
    expect(query.range.mock.calls).toEqual([
      [0, 1],
      [2, 3],
      [4, 5],
    ]);
  });

  it('stops after an empty page when the total is an exact multiple of the page size', async () => {
    const { supabase, query } = createPagedSupabase([
      { data: makeEntries(2), error: null },
      { data: [], error: null },
    ]);

    const entries = await fetchNewsletterSitemapEntries(supabase, 2);

    expect(entries).toHaveLength(2);
    expect(query.range).toHaveBeenCalledTimes(2);
  });

  it('throws with context when the query fails', async () => {
    const { supabase } = createPagedSupabase([{ data: null, error: { message: 'boom' } }]);

    await expect(fetchNewsletterSitemapEntries(supabase)).rejects.toThrow(
      'Failed to fetch newsletters for sitemap: boom',
    );
  });
});
