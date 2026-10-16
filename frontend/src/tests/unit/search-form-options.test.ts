import { describe, it, expect } from 'vitest';
import {
  buildSourceOptions,
  extractSourceTypes,
  extractWardNumbers,
} from '../../lib/server/search-form-options';
import type { SearchSourceRow } from '../../lib/server/search-form-options';

const SOURCES: SearchSourceRow[] = [
  { id: 51, name: 'Chicago Transit Authority', ward_number: null, source_type: 'agency' },
  { id: 10, name: 'Ward Ten Alder', ward_number: '10', source_type: 'alderman' },
  { id: 2, name: 'Ward Two Alder', ward_number: '2', source_type: 'alderman' },
  { id: 40, name: 'Andre Vasquez', ward_number: '40', source_type: 'alderman' },
  { id: 41, name: 'Another Ward 40 Office', ward_number: '40', source_type: 'alderman' },
  { id: 60, name: 'Board of Elections', ward_number: null, source_type: 'agency' },
];

describe('buildSourceOptions', () => {
  it('orders ward offices numerically, then other sources by name, with ward labels', () => {
    expect(buildSourceOptions(SOURCES)).toEqual([
      { id: 2, label: 'Ward 2 – Ward Two Alder' },
      { id: 10, label: 'Ward 10 – Ward Ten Alder' },
      { id: 40, label: 'Ward 40 – Andre Vasquez' },
      { id: 41, label: 'Ward 40 – Another Ward 40 Office' },
      { id: 60, label: 'Board of Elections' },
      { id: 51, label: 'Chicago Transit Authority' },
    ]);
  });

  it('does not mutate its input', () => {
    const input = [...SOURCES];
    buildSourceOptions(input);
    expect(input).toEqual(SOURCES);
  });
});

describe('extractWardNumbers', () => {
  it('returns distinct wards in numeric order, skipping sources without a ward', () => {
    expect(extractWardNumbers(SOURCES)).toEqual(['2', '10', '40']);
  });
});

describe('extractSourceTypes', () => {
  it('returns distinct source types alphabetically', () => {
    expect(extractSourceTypes(SOURCES)).toEqual(['agency', 'alderman']);
  });
});
