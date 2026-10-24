import { describe, it, expect } from 'vitest';
import { addDaysToIsoDate, parseIsoDate, startOfChicagoDayUtc } from '../../lib/chicago-dates';

describe('parseIsoDate', () => {
  it.each(['2026-01-15', '2024-02-29', '2026-12-31'])('accepts real date %s', (value) => {
    expect(parseIsoDate(value)).toBe(value);
  });

  it('trims surrounding whitespace', () => {
    expect(parseIsoDate(' 2026-01-15 ')).toBe('2026-01-15');
  });

  it.each([null, undefined, '', '2026-02-29', '2026-04-31', '2026-00-10', '2026-1-5', '15/01/2026', '2026-01-15T00:00', 'x2026-01-15'])(
    'rejects %j',
    (value) => {
      expect(parseIsoDate(value)).toBeNull();
    },
  );

  it('rejects years before 100, which Date.UTC reads as 19xx', () => {
    expect(parseIsoDate('0050-01-01')).toBeNull();
  });
});

describe('addDaysToIsoDate', () => {
  it('rolls over month and year boundaries', () => {
    expect(addDaysToIsoDate('2026-01-31', 1)).toBe('2026-02-01');
    expect(addDaysToIsoDate('2026-12-31', 1)).toBe('2027-01-01');
    expect(addDaysToIsoDate('2024-02-28', 1)).toBe('2024-02-29');
  });
});

describe('startOfChicagoDayUtc', () => {
  it('uses the CST offset in winter', () => {
    expect(startOfChicagoDayUtc('2026-01-15')).toBe('2026-01-15T06:00:00.000Z');
  });

  it('uses the CDT offset in summer', () => {
    expect(startOfChicagoDayUtc('2026-07-04')).toBe('2026-07-04T05:00:00.000Z');
  });

  it('handles the days daylight saving time starts and ends', () => {
    // DST starts 2026-03-08 and ends 2026-11-01 at 2am local; midnight is still on the prior offset.
    expect(startOfChicagoDayUtc('2026-03-08')).toBe('2026-03-08T06:00:00.000Z');
    expect(startOfChicagoDayUtc('2026-03-09')).toBe('2026-03-09T05:00:00.000Z');
    expect(startOfChicagoDayUtc('2026-11-01')).toBe('2026-11-01T05:00:00.000Z');
    expect(startOfChicagoDayUtc('2026-11-02')).toBe('2026-11-02T06:00:00.000Z');
  });
});
