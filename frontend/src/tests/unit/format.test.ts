import { describe, it, expect } from 'vitest';
import { humanizeIdentifier } from '../../lib/format';

describe('humanizeIdentifier', () => {
  it.each([
    ['bike_lanes', 'Bike Lanes'],
    ['4_flats_legalization', '4 Flats Legalization'],
    ['alderman', 'Alderman'],
    ['double__underscore_', 'Double Underscore'],
  ])('formats %s as %s', (identifier, expected) => {
    expect(humanizeIdentifier(identifier)).toBe(expected);
  });
});
