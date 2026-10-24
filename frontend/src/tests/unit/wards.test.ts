import { describe, it, expect } from 'vitest';
import {
  ALL_WARD_NUMBERS,
  buildWardContactLinks,
  buildWardDirectory,
  buildWardPath,
  buildWardSearchPath,
  formatAlderNames,
  formatOrdinal,
  formatWardAldermanHeading,
  formatWardName,
  parseWardParam,
  type WardContactSource,
} from '../../lib/wards';

describe('parseWardParam', () => {
  it.each([
    ['1', 1],
    ['9', 9],
    ['10', 10],
    ['50', 50],
  ])('accepts canonical ward "%s"', (raw, expected) => {
    expect(parseWardParam(raw)).toBe(expected);
  });

  it.each(['0', '51', '100', '05', '-1', '+1', '1.0', '1e1', ' 1', 'abc', '', '١'])(
    'rejects "%s"',
    (raw) => {
      expect(parseWardParam(raw)).toBeNull();
    },
  );

  it('rejects a missing parameter', () => {
    expect(parseWardParam(undefined)).toBeNull();
  });
});

describe('ward paths', () => {
  it('builds the ward page path', () => {
    expect(buildWardPath(7)).toBe('/ward/7');
  });

  it('builds a search path filtered to the ward', () => {
    expect(buildWardSearchPath(42)).toBe('/search?ward=42');
  });
});

describe('formatAlderNames', () => {
  it('returns null for no names', () => {
    expect(formatAlderNames([])).toBeNull();
  });

  it('returns a single name unchanged', () => {
    expect(formatAlderNames(['Maria Hadden'])).toBe('Maria Hadden');
  });

  it('joins two names with "and"', () => {
    expect(formatAlderNames(['A', 'B'])).toBe('A and B');
  });

  it('uses a serial comma for three or more names', () => {
    expect(formatAlderNames(['A', 'B', 'C'])).toBe('A, B, and C');
  });
});

describe('buildWardDirectory', () => {
  const source = (name: string, ward_number: string | null) => ({ name, ward_number });

  it('returns one entry per ward in order, even with no sources', () => {
    const directory = buildWardDirectory([]);
    expect(directory.map((entry) => entry.wardNumber)).toEqual([...ALL_WARD_NUMBERS]);
    expect(directory).toHaveLength(50);
    expect(directory.every((entry) => entry.sources.length === 0)).toBe(true);
  });

  it('groups sources by ward, keeping input order within a ward', () => {
    const directory = buildWardDirectory([
      source('New Alder', '2'),
      source('First Alder', '1'),
      source('Former Alder', '2'),
    ]);
    expect(directory[0].sources.map((s) => s.name)).toEqual(['First Alder']);
    expect(directory[1].sources.map((s) => s.name)).toEqual(['New Alder', 'Former Alder']);
  });

  it('tolerates surrounding whitespace in stored ward numbers', () => {
    expect(buildWardDirectory([source('Padded', ' 3 ')])[2].sources).toHaveLength(1);
  });

  it('ignores sources without a valid ward number', () => {
    const directory = buildWardDirectory([
      source('Agency', null),
      source('Out of range', '51'),
      source('Garbage', 'north'),
    ]);
    expect(directory.every((entry) => entry.sources.length === 0)).toBe(true);
  });
});

describe('buildWardContactLinks', () => {
  const fullSource: WardContactSource = {
    website: 'https://www.the1stward.com/',
    phone: '872-206-2685',
    email_address: 'info@the1stward.com',
  };

  it('returns every available link in display order', () => {
    expect(buildWardContactLinks(fullSource)).toEqual([
      { kind: 'website', label: 'Website', href: 'https://www.the1stward.com/', isExternal: true },
      { kind: 'phone', label: '872-206-2685', href: 'tel:8722062685', isExternal: false },
      {
        kind: 'email',
        label: 'info@the1stward.com',
        href: 'mailto:info@the1stward.com',
        isExternal: false,
      },
    ]);
  });

  it('omits missing and blank fields', () => {
    expect(
      buildWardContactLinks({ website: '  ', phone: null, email_address: null }),
    ).toEqual([]);
  });

  it('drops web links that are not absolute http(s) URLs', () => {
    const links = buildWardContactLinks({
      ...fullSource,
      website: 'javascript:alert(1)',
    });
    expect(links.map((link) => link.kind)).toEqual(['phone', 'email']);
  });

  it('drops a phone number with no digits', () => {
    const links = buildWardContactLinks({ ...fullSource, phone: 'TBD' });
    expect(links.map((link) => link.kind)).not.toContain('phone');
  });

  it('trims whitespace from the email address', () => {
    const links = buildWardContactLinks({ ...fullSource, email_address: ' ward@example.org ' });
    expect(links.find((link) => link.kind === 'email')?.href).toBe('mailto:ward@example.org');
  });
});

describe('formatOrdinal', () => {
  it.each([
    [1, '1st'],
    [2, '2nd'],
    [3, '3rd'],
    [4, '4th'],
    [11, '11th'],
    [12, '12th'],
    [13, '13th'],
    [21, '21st'],
    [22, '22nd'],
    [23, '23rd'],
    [50, '50th'],
  ])('formats %i as %s', (value, expected) => {
    expect(formatOrdinal(value)).toBe(expected);
  });
});

describe('formatWardName', () => {
  it('uses the ordinal ward name people search for', () => {
    expect(formatWardName(38)).toBe('38th Ward');
  });
});

describe('formatWardAldermanHeading', () => {
  it('names a single alderman', () => {
    expect(formatWardAldermanHeading(38, ['Nicholas Sposato'])).toBe(
      '38th Ward Alderman Nicholas Sposato',
    );
  });

  it('uses the plural for several aldermen', () => {
    expect(formatWardAldermanHeading(1, ['A', 'B', 'C'])).toBe('1st Ward Aldermen A, B, and C');
  });

  it('is just the ward name when no alderman is on file', () => {
    expect(formatWardAldermanHeading(12, [])).toBe('12th Ward');
  });
});
