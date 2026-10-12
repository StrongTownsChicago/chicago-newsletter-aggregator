import { describe, it, expect } from 'vitest';
import { NEWSLETTERS_PER_PAGE, countPages, getPageRange, parsePageParam } from '../../lib/pagination';

describe('parsePageParam', () => {
  it.each([
    ['1', 1],
    ['3', 3],
  ])('parses "%s"', (raw, expected) => {
    expect(parsePageParam(raw)).toBe(expected);
  });

  it.each([null, '', '0', '-2', '1.5', 'abc'])('falls back to page 1 for %s', (raw) => {
    expect(parsePageParam(raw)).toBe(1);
  });
});

describe('getPageRange', () => {
  it('returns an inclusive range for the first page', () => {
    expect(getPageRange(1)).toEqual({ from: 0, to: NEWSLETTERS_PER_PAGE - 1 });
  });

  it('offsets later pages by the page size', () => {
    expect(getPageRange(3, 10)).toEqual({ from: 20, to: 29 });
  });
});

describe('countPages', () => {
  it.each([
    [0, 0],
    [1, 1],
    [20, 1],
    [21, 2],
  ])('needs %i rows -> %i pages', (total, expected) => {
    expect(countPages(total, 20)).toBe(expected);
  });
});
