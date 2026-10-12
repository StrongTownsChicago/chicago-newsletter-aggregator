import { describe, it, expect } from 'vitest';
import { humanizeIdentifier } from '../../lib/format';
import { ALL_TOPICS } from '../../lib/topics';

describe('humanizeIdentifier', () => {
  it.each([
    ['bike_lanes', 'Bike Lanes'],
    ['4_flats_legalization', '4 Flats Legalization'],
    ['alderman', 'Alderman'],
    ['double__underscore_', 'Double Underscore'],
  ])('formats %s as %s', (identifier, expected) => {
    expect(humanizeIdentifier(identifier)).toBe(expected);
  });

  it('produces a non-empty label without underscores for every canonical topic', () => {
    for (const topic of ALL_TOPICS) {
      const label = humanizeIdentifier(topic);
      expect(label).not.toContain('_');
      expect(label.length).toBeGreaterThan(0);
    }
  });
});
