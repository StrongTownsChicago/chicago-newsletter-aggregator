import { describe, expect, it } from 'vitest';
import wardGlanceData from '../../data/ward-glance.json';
import {
  describeCadence,
  describeCityReach,
  describeTopicShare,
  describeTrackedPeriod,
  findWardGlance,
  listTrackedMonths,
  listWardMonthCounts,
  type WardGlance,
  type WardGlanceFile,
} from '../../lib/ward-glance';

function makeGlance(overrides: Partial<WardGlance> = {}): WardGlance {
  return {
    first_date: '2026-08-20',
    last_date: '2026-10-01',
    newsletters: 3,
    recent_months: [null, 2, 1],
    per_month: 1.5,
    topic_newsletters: 3,
    topics: [{ id: 'schools', newsletters: 2, city_wards: 25 }],
    terms: ['wicker park'],
    ...overrides,
  };
}

function makeFile(glance: WardGlance): WardGlanceFile {
  return {
    data_through: '2026-10-13',
    topics: { schools: 'Schools' },
    min_share_newsletters: 20,
    latest_month: '2026-09',
    window_months: ['2026-07', '2026-08', '2026-09'],
    city_readable_wards: 37,
    wards: { '8': glance },
  };
}

describe('findWardGlance', () => {
  it('returns the ward summary, or null for wards without newsletters', () => {
    const glance = makeGlance();
    const file = makeFile(glance);
    expect(findWardGlance(file, 8)).toBe(glance);
    expect(findWardGlance(file, 9)).toBeNull();
  });
});

describe('month counts', () => {
  it('pairs window months with counts and marks months before the archive', () => {
    const glance = makeGlance();
    const counts = listWardMonthCounts(makeFile(glance), glance);
    expect(counts).toEqual([
      { month: '2026-07', newsletters: null },
      { month: '2026-08', newsletters: 2 },
      { month: '2026-09', newsletters: 1 },
    ]);
    const tracked = listTrackedMonths(counts);
    expect(tracked).toEqual(['2026-08', '2026-09']);
    expect(describeTrackedPeriod(tracked)).toBe('August to September 2026');
    expect(describeTrackedPeriod([])).toBeNull();
  });
});

describe('describeCadence', () => {
  it('rounds to one decimal and uses the singular for one', () => {
    expect(describeCadence(makeGlance({ per_month: 4.7 }))).toBe('About 4.7 newsletters a month');
    expect(describeCadence(makeGlance({ per_month: 1 }))).toBe('About 1 newsletter a month');
  });

  it('says nothing when no newsletters were sent in the window', () => {
    expect(describeCadence(makeGlance({ per_month: 0 }))).toBeNull();
    expect(describeCadence(makeGlance({ per_month: null }))).toBeNull();
  });
});

describe('describeTopicShare', () => {
  it('quotes a percentage only with enough newsletters', () => {
    expect(describeTopicShare(23, 28, 20)).toEqual({
      percent: 82,
      fraction: 23 / 28,
      countLabel: '23 of 28 newsletters',
    });
    expect(describeTopicShare(1, 1, 20)).toEqual({
      percent: null,
      fraction: 1,
      countLabel: '1 of 1 newsletter',
    });
  });
});

describe('describeCityReach', () => {
  it('describes how many wards mentioned the topic in the latest month', () => {
    const file = makeFile(makeGlance());
    expect(describeCityReach(file, { id: 'schools', newsletters: 2, city_wards: 25 })).toBe(
      'Citywide, 25 of 37 wards mentioned it in September 2026',
    );
    expect(describeCityReach({ ...file, latest_month: null }, file.wards['8'].topics[0])).toBeNull();
  });
});

describe('committed ward-glance.json', () => {
  const file = wardGlanceData as WardGlanceFile;

  it('stays small, since the server bundle includes it', () => {
    const MAX_BYTES = 60_000;
    expect(JSON.stringify(file).length).toBeLessThan(MAX_BYTES);
  });

  it('labels every topic and aligns month counts with the window', () => {
    for (const glance of Object.values(file.wards)) {
      expect(glance.recent_months).toHaveLength(file.window_months.length);
      for (const topic of glance.topics) {
        expect(file.topics[topic.id]).toBeTruthy();
      }
    }
  });
});
