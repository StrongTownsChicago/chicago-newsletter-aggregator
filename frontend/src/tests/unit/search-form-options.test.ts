import { describe, it, expect } from 'vitest';
import { buildSourceNames, buildWardOptions } from '../../lib/server/search-form-options';
import type { SearchSourceRow } from '../../lib/server/search-form-options';

const SOURCES: SearchSourceRow[] = [
  { id: 51, name: 'Chicago Transit Authority', ward_number: null },
  { id: 10, name: 'Ward Ten Alder', ward_number: '10' },
  { id: 2, name: 'Ward Two Alder', ward_number: '2' },
  { id: 41, name: 'Previous Ward 40 Office', ward_number: '40' },
  { id: 40, name: 'Andre Vasquez', ward_number: '40' },
];

describe('buildWardOptions', () => {
  it('lists wards numerically, labelled with their sources, skipping sources without a ward', () => {
    expect(buildWardOptions(SOURCES)).toEqual([
      { ward: '2', label: 'Ward 2 – Ward Two Alder' },
      { ward: '10', label: 'Ward 10 – Ward Ten Alder' },
      { ward: '40', label: 'Ward 40 – Andre Vasquez, Previous Ward 40 Office' },
    ]);
  });

  it('does not mutate its input', () => {
    const input = [...SOURCES];
    buildWardOptions(input);
    expect(input).toEqual(SOURCES);
  });
});

describe('buildSourceNames', () => {
  it('maps source ids to names', () => {
    const names = buildSourceNames(SOURCES);
    expect(names.get(51)).toBe('Chicago Transit Authority');
    expect(names.get(40)).toBe('Andre Vasquez');
    expect(names.size).toBe(SOURCES.length);
  });
});
