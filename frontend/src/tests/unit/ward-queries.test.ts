import { describe, it, expect, vi } from 'vitest';
import type { SupabaseClient } from '@supabase/supabase-js';
import {
  EMPTY_WARD_NEWSLETTER_PAGE,
  fetchWardDirectorySources,
  fetchWardNewsletterPage,
  fetchWardSources,
} from '../../lib/ward-queries';
import {
  SOURCE_WARD_DIRECTORY_SELECT,
  SOURCE_WARD_PROFILE_SELECT,
  buildNewsletterCardSelect,
} from '../../lib/newsletter-queries';

type QueryResult = { data?: unknown; count?: number | null; error: { message: string } | null };

/**
 * A chainable PostgREST query stub. Every builder method records its call and
 * returns the stub; awaiting the stub resolves to `result`.
 */
const createQuery = (result: QueryResult) => {
  const query = {
    select: vi.fn(),
    eq: vi.fn(),
    in: vi.fn(),
    order: vi.fn(),
    range: vi.fn(),
    limit: vi.fn(),
    then: (resolve: (value: QueryResult) => unknown) => Promise.resolve(result).then(resolve),
  };
  for (const method of ['select', 'eq', 'in', 'order', 'range', 'limit'] as const) {
    query[method].mockReturnValue(query);
  }
  return query;
};

const createSupabase = (results: QueryResult[]) => {
  const queries = results.map(createQuery);
  const from = vi.fn();
  queries.forEach((query) => from.mockReturnValueOnce(query));
  return { supabase: { from } as unknown as SupabaseClient, from, queries };
};

describe('fetchWardSources', () => {
  it('queries alderman sources for the ward with the profile columns', async () => {
    const rows = [{ id: 1, name: 'Daniel La Spata', ward_number: '1' }];
    const { supabase, from, queries } = createSupabase([{ data: rows, error: null }]);

    await expect(fetchWardSources(supabase, 1)).resolves.toEqual(rows);

    expect(from).toHaveBeenCalledWith('sources');
    expect(queries[0].select).toHaveBeenCalledWith(SOURCE_WARD_PROFILE_SELECT);
    expect(queries[0].eq).toHaveBeenCalledWith('source_type', 'alderman');
    expect(queries[0].eq).toHaveBeenCalledWith('ward_number', '1');
  });

  it('returns an empty list when the ward has no sources', async () => {
    const { supabase } = createSupabase([{ data: null, error: null }]);
    await expect(fetchWardSources(supabase, 7)).resolves.toEqual([]);
  });

  it('throws with context when the query fails', async () => {
    const { supabase } = createSupabase([{ data: null, error: { message: 'boom' } }]);
    await expect(fetchWardSources(supabase, 7)).rejects.toThrow(
      'Failed to fetch sources for ward 7: boom',
    );
  });
});

describe('fetchWardDirectorySources', () => {
  it('fetches all alderman sources in a single query', async () => {
    const { supabase, from, queries } = createSupabase([{ data: [], error: null }]);

    await fetchWardDirectorySources(supabase);

    expect(from).toHaveBeenCalledTimes(1);
    expect(queries[0].select).toHaveBeenCalledWith(SOURCE_WARD_DIRECTORY_SELECT);
    expect(queries[0].eq).toHaveBeenCalledWith('source_type', 'alderman');
  });

  it('throws with context when the query fails', async () => {
    const { supabase } = createSupabase([{ data: null, error: { message: 'down' } }]);
    await expect(fetchWardDirectorySources(supabase)).rejects.toThrow(
      'Failed to fetch ward directory sources: down',
    );
  });
});

describe('fetchWardNewsletterPage', () => {
  const newsletter = { id: 'a', subject: 'Hello', received_date: '2026-10-01T12:00:00Z' };

  it('skips querying when there are no sources', async () => {
    const { supabase, from } = createSupabase([]);
    await expect(fetchWardNewsletterPage(supabase, [], 1)).resolves.toEqual(EMPTY_WARD_NEWSLETTER_PAGE);
    expect(from).not.toHaveBeenCalled();
  });

  it('returns the page, total count, and latest date across all ward sources', async () => {
    const { supabase, queries } = createSupabase([
      { data: [newsletter], error: null },
      { count: 41, error: null },
      { data: [{ received_date: '2026-10-05T12:00:00Z' }], error: null },
    ]);

    const result = await fetchWardNewsletterPage(supabase, [3, 9], 3);

    expect(result).toEqual({
      newsletters: [newsletter],
      totalCount: 41,
      latestReceivedDate: '2026-10-05T12:00:00Z',
    });
    const [listQuery, countQuery, latestQuery] = queries;
    expect(listQuery.select).toHaveBeenCalledWith(buildNewsletterCardSelect({ filtersOnSource: false }));
    expect(listQuery.in).toHaveBeenCalledWith('source_id', [3, 9]);
    expect(listQuery.order).toHaveBeenCalledWith('received_date', { ascending: false });
    expect(listQuery.range).toHaveBeenCalledWith(40, 59);
    expect(countQuery.select).toHaveBeenCalledWith('id', { count: 'exact', head: true });
    expect(countQuery.in).toHaveBeenCalledWith('source_id', [3, 9]);
    expect(latestQuery.limit).toHaveBeenCalledWith(1);
  });

  it('reports no latest date when the ward has no newsletters', async () => {
    const { supabase } = createSupabase([
      { data: [], error: null },
      { count: 0, error: null },
      { data: [], error: null },
    ]);

    await expect(fetchWardNewsletterPage(supabase, [3], 1)).resolves.toEqual(EMPTY_WARD_NEWSLETTER_PAGE);
  });

  it('throws with context when any query fails', async () => {
    const { supabase } = createSupabase([
      { data: [], error: null },
      { count: null, error: { message: 'timeout' } },
      { data: [], error: null },
    ]);

    await expect(fetchWardNewsletterPage(supabase, [3], 1)).rejects.toThrow(
      'Failed to fetch newsletters for sources 3: timeout',
    );
  });
});
