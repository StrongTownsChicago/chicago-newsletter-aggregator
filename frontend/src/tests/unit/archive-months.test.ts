import { describe, expect, it } from 'vitest';
import {
  formatLongDate,
  formatLongMonth,
  formatMonthRange,
  formatShortMonthName,
  monthOfDate,
} from '../../lib/archive-months';

describe('archive month labels', () => {
  it('formats months and dates without shifting across time zones', () => {
    expect(formatLongMonth('2026-09')).toBe('September 2026');
    expect(formatLongMonth('2026-01')).toBe('January 2026');
    expect(formatShortMonthName('2026-12')).toBe('Dec');
    expect(formatLongDate('2026-10-01')).toBe('October 1, 2026');
    expect(monthOfDate('2026-10-01')).toBe('2026-10');
  });

  it('names a range once per year', () => {
    expect(formatMonthRange('2026-04', '2026-09')).toBe('April to September 2026');
    expect(formatMonthRange('2025-11', '2026-04')).toBe('November 2025 to April 2026');
    expect(formatMonthRange('2026-09', '2026-09')).toBe('September 2026');
  });
});
