import { describe, it, expect } from 'vitest';
import {
  DEFAULT_SEARCH_SORT,
  EMPTY_SEARCH_FILTERS as EMPTY_FILTERS,
  SEARCH_PATH,
  applySearchFilters,
  applySearchSort,
  buildSearchBaseUrl,
  buildSearchUrlWithoutFilters,
  getPageRange,
  listActiveSearchFilters,
  parseSearchParams,
  requiresSourceJoin,
} from '../../lib/search-filters';
import type { FilterableQuery, SearchFilters, SortableQuery } from '../../lib/search-filters';

const parse = (queryString: string) => parseSearchParams(new URLSearchParams(queryString));

type RecordedCall = [method: string, ...args: unknown[]];

/** Chainable query builder stub that records every filter/order call in sequence. */
class RecordingQuery implements FilterableQuery, SortableQuery {
  readonly calls: RecordedCall[] = [];

  private record(method: string, args: unknown[]): this {
    this.calls.push([method, ...args]);
    return this;
  }

  textSearch(...args: Parameters<FilterableQuery['textSearch']>) {
    return this.record('textSearch', args);
  }
  eq(...args: Parameters<FilterableQuery['eq']>) {
    return this.record('eq', args);
  }
  contains(...args: Parameters<FilterableQuery['contains']>) {
    return this.record('contains', args);
  }
  gte(...args: Parameters<FilterableQuery['gte']>) {
    return this.record('gte', args);
  }
  lt(...args: Parameters<FilterableQuery['lt']>) {
    return this.record('lt', args);
  }
  order(...args: Parameters<SortableQuery['order']>) {
    return this.record('order', args);
  }
}

describe('parseSearchParams', () => {
  it('returns empty filters, default sort, and page 1 when no params are given', () => {
    expect(parse('')).toEqual({ filters: EMPTY_FILTERS, sort: DEFAULT_SEARCH_SORT, page: 1 });
  });

  it('parses every supported filter', () => {
    const { filters, sort, page } = parse(
      'q=bike+lanes&ward=40&source=12&source_type=alderman&topic=bike_lanes' +
        '&from=2026-01-01&to=2026-03-31&sort=oldest&page=3',
    );

    expect(filters).toEqual({
      query: 'bike lanes',
      ward: '40',
      sourceId: 12,
      sourceType: 'alderman',
      topic: 'bike_lanes',
      fromDate: '2026-01-01',
      toDate: '2026-03-31',
    });
    expect(sort).toBe('oldest');
    expect(page).toBe(3);
  });

  it('trims whitespace and treats blank values as absent', () => {
    const { filters } = parse('q=%20%20zoning%20&ward=&topic=&source=%20&from=');
    expect(filters).toEqual({ ...EMPTY_FILTERS, query: 'zoning' });
  });

  describe('page', () => {
    it.each(['0', '-2', 'abc', '1.5', '', '99999999999999999999'])(
      'falls back to page 1 for %j',
      (value) => {
        expect(parse(`page=${value}`).page).toBe(1);
      },
    );
  });

  describe('sort', () => {
    it.each(['newest', 'oldest'])('accepts %s', (value) => {
      expect(parse(`sort=${value}`).sort).toBe(value);
    });

    it.each(['popular', 'OLDEST', ''])('falls back to the default for %j', (value) => {
      expect(parse(`sort=${value}`).sort).toBe(DEFAULT_SEARCH_SORT);
    });
  });

  describe('topic', () => {
    it('ignores topics outside the canonical list', () => {
      expect(parse('topic=not_a_topic').filters.topic).toBeNull();
    });
  });

  describe('removed relevance params from old links', () => {
    it('ignores min_relevance and sort=relevance', () => {
      expect(parse('min_relevance=5&sort=relevance')).toEqual({
        filters: EMPTY_FILTERS,
        sort: DEFAULT_SEARCH_SORT,
        page: 1,
      });
    });

    it('keeps the other filters from an old link', () => {
      const { filters, sort } = parse('q=zoning&min_relevance=7&sort=relevance');
      expect(filters).toEqual({ ...EMPTY_FILTERS, query: 'zoning' });
      expect(sort).toBe(DEFAULT_SEARCH_SORT);
    });
  });

  describe('source and ward', () => {
    it.each(['0', '-3', 'abc', '2.5'])('ignores invalid source id %j', (value) => {
      expect(parse(`source=${value}`).filters.sourceId).toBeNull();
    });

    it('normalizes ward numbers with leading zeros', () => {
      expect(parse('ward=05').filters.ward).toBe('5');
    });

    it.each(['0', 'abc', '1;drop'])('ignores invalid ward %j', (value) => {
      expect(parse(`ward=${value}`).filters.ward).toBeNull();
    });

    it('ignores malformed source types', () => {
      expect(parse('source_type=Alder%20Man').filters.sourceType).toBeNull();
    });
  });

  describe('date range', () => {
    it.each(['2026-02-30', '2026-13-01', '01/15/2026', 'yesterday', '2026-1-5'])(
      'ignores invalid date %j',
      (value) => {
        const { filters } = parse(`from=${value}&to=${value}`);
        expect(filters.fromDate).toBeNull();
        expect(filters.toDate).toBeNull();
      },
    );

    it('keeps a valid bound when the other is invalid', () => {
      const { filters } = parse('from=garbage&to=2026-04-01');
      expect(filters.fromDate).toBeNull();
      expect(filters.toDate).toBe('2026-04-01');
    });

    it('swaps a reversed range so it still matches', () => {
      const { filters } = parse('from=2026-05-01&to=2026-04-01');
      expect(filters.fromDate).toBe('2026-04-01');
      expect(filters.toDate).toBe('2026-05-01');
    });
  });
});

describe('buildSearchBaseUrl', () => {
  it('returns the bare search path when nothing is set', () => {
    expect(buildSearchBaseUrl(EMPTY_FILTERS, DEFAULT_SEARCH_SORT)).toBe(SEARCH_PATH);
  });

  it('omits the default sort but keeps a non-default one', () => {
    expect(buildSearchBaseUrl(EMPTY_FILTERS, 'oldest')).toBe('/search?sort=oldest');
  });

  it('never includes the page parameter', () => {
    const { filters, sort } = parse('q=zoning&page=4');
    expect(buildSearchBaseUrl(filters, sort)).toBe('/search?q=zoning');
  });

  it('round-trips every filter through parseSearchParams', () => {
    const original = parse(
      'q=bike+lanes&ward=40&source=12&source_type=alderman&topic=bike_lanes' +
        '&from=2026-01-01&to=2026-03-31&sort=oldest',
    );
    const baseUrl = buildSearchBaseUrl(original.filters, original.sort);
    const reparsed = parseSearchParams(new URL(baseUrl, 'http://localhost').searchParams);

    expect(reparsed).toEqual({ ...original, page: 1 });
  });

  it('drops invalid params from the URL', () => {
    const { filters, sort } = parse('topic=bogus&sort=weird&from=2026-02-31&q=transit');
    expect(buildSearchBaseUrl(filters, sort)).toBe('/search?q=transit');
  });
});

describe('requiresSourceJoin', () => {
  it('is false without source-table filters', () => {
    expect(requiresSourceJoin(EMPTY_FILTERS)).toBe(false);
  });

  it('is false for a source id filter, which uses newsletters.source_id', () => {
    expect(requiresSourceJoin({ ...EMPTY_FILTERS, sourceId: 3 })).toBe(false);
  });

  it.each([
    ['ward', { ward: '1' }],
    ['source type', { sourceType: 'alderman' }],
  ])('is true for a %s filter', (_, overrides) => {
    expect(requiresSourceJoin({ ...EMPTY_FILTERS, ...overrides })).toBe(true);
  });
});

describe('getPageRange', () => {
  it('returns the inclusive zero-based row range for a page', () => {
    expect(getPageRange(1, 20)).toEqual({ start: 0, end: 19 });
    expect(getPageRange(3, 20)).toEqual({ start: 40, end: 59 });
  });
});

describe('applySearchFilters', () => {
  const applyTo = (filters: SearchFilters) => applySearchFilters(new RecordingQuery(), filters).calls;

  it('applies no filters when none are set', () => {
    expect(applyTo(EMPTY_FILTERS)).toEqual([]);
  });

  it('returns the same chained builder', () => {
    const query = new RecordingQuery();
    expect(applySearchFilters(query, { ...EMPTY_FILTERS, topic: 'bike_lanes' })).toBe(query);
  });

  it('applies keyword search as an English websearch on the search vector', () => {
    expect(applyTo({ ...EMPTY_FILTERS, query: 'bike lanes' })).toEqual([
      ['textSearch', 'search_vector', 'bike lanes', { type: 'websearch', config: 'english' }],
    ]);
  });

  it('filters by source id, source type, ward, and topic', () => {
    expect(
      applyTo({ ...EMPTY_FILTERS, sourceId: 12, sourceType: 'alderman', ward: '40', topic: 'bike_lanes' }),
    ).toEqual([
      ['eq', 'source_id', 12],
      ['eq', 'sources.source_type', 'alderman'],
      ['eq', 'sources.ward_number', '40'],
      ['contains', 'topics', ['bike_lanes']],
    ]);
  });

  it('converts the date range to Chicago day boundaries with an inclusive end date', () => {
    expect(applyTo({ ...EMPTY_FILTERS, fromDate: '2026-01-15', toDate: '2026-01-31' })).toEqual([
      ['gte', 'received_date', '2026-01-15T06:00:00.000Z'],
      ['lt', 'received_date', '2026-02-01T06:00:00.000Z'],
    ]);
  });

  it('includes the whole day for a single-day range during daylight saving time', () => {
    expect(applyTo({ ...EMPTY_FILTERS, fromDate: '2026-07-04', toDate: '2026-07-04' })).toEqual([
      ['gte', 'received_date', '2026-07-04T05:00:00.000Z'],
      ['lt', 'received_date', '2026-07-05T05:00:00.000Z'],
    ]);
  });

  it('applies identical filters to separate count and data queries', () => {
    const { filters } = parse(
      'q=zoning&ward=40&source=12&topic=bike_lanes&from=2026-01-01&to=2026-03-31',
    );
    const countCalls = applySearchFilters(new RecordingQuery(), filters).calls;
    const dataCalls = applySearchFilters(new RecordingQuery(), filters).calls;

    expect(countCalls).toEqual(dataCalls);
    expect(countCalls).toHaveLength(6);
  });
});

describe('applySearchSort', () => {
  const sortCalls = (sort: Parameters<typeof applySearchSort>[1]) =>
    applySearchSort(new RecordingQuery(), sort).calls;

  it('sorts newest first by default', () => {
    expect(sortCalls('newest')).toEqual([['order', 'received_date', { ascending: false }]]);
  });

  it('sorts oldest first', () => {
    expect(sortCalls('oldest')).toEqual([['order', 'received_date', { ascending: true }]]);
  });
});

describe('listActiveSearchFilters', () => {
  const SOURCE_NAMES = new Map([[51, 'Chicago Transit Authority']]);

  it('is empty when only keywords are set', () => {
    expect(listActiveSearchFilters({ ...EMPTY_FILTERS, query: 'zoning' }, 'newest', SOURCE_NAMES)).toEqual([]);
  });

  it('labels each filter and links to the search without it', () => {
    const filters: SearchFilters = {
      query: 'bike lanes',
      ward: '40',
      sourceId: 51,
      sourceType: 'agency',
      topic: 'bike_lanes',
      fromDate: '2026-01-01',
      toDate: '2026-06-30',
    };

    const active = listActiveSearchFilters(filters, 'oldest', SOURCE_NAMES);

    expect(active.map(({ key, label }) => [key, label])).toEqual([
      ['topic', 'Bike lanes'],
      ['ward', 'Ward 40'],
      ['sourceId', 'Chicago Transit Authority'],
      ['sourceType', 'Agency'],
      ['fromDate', 'From January 1, 2026'],
      ['toDate', 'To June 30, 2026'],
    ]);
    for (const { key, removeUrl } of active) {
      expect(parse(removeUrl.split('?')[1])).toEqual({
        filters: { ...filters, [key]: null },
        sort: 'oldest',
        page: 1,
      });
    }
  });

  it('falls back to the source id when the source name is unknown', () => {
    const [sourceFilter] = listActiveSearchFilters({ ...EMPTY_FILTERS, sourceId: 7 }, 'newest', new Map());
    expect(sourceFilter.label).toBe('Source 7');
  });
});

describe('buildSearchUrlWithoutFilters', () => {
  it('keeps the keywords and sort and drops every filter', () => {
    const filters: SearchFilters = { ...EMPTY_FILTERS, query: 'zoning', ward: '1', topic: 'bike_lanes' };
    expect(buildSearchUrlWithoutFilters(filters, 'oldest')).toBe(`${SEARCH_PATH}?q=zoning&sort=oldest`);
  });

  it('returns the bare search path without keywords', () => {
    expect(buildSearchUrlWithoutFilters({ ...EMPTY_FILTERS, ward: '1' }, DEFAULT_SEARCH_SORT)).toBe(SEARCH_PATH);
  });
});
