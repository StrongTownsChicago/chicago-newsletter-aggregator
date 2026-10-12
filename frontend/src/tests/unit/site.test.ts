import { describe, it, expect } from 'vitest';
import {
  HOME_PATH,
  PREFERENCES_PATH,
  buildPrimaryNavItems,
  isNavItemActive,
  type NavItem,
} from '../../lib/site';
import { SEARCH_PATH } from '../../lib/search-filters';
import { WARD_DIRECTORY_PATH } from '../../lib/wards';

function findNavItem(label: string): NavItem {
  const item = buildPrimaryNavItems({ showPreferences: true }).find(
    (navItem) => navItem.label === label,
  );
  if (!item) {
    throw new Error(`No nav item labelled ${label}`);
  }
  return item;
}

describe('buildPrimaryNavItems', () => {
  it('lists the public sections in order when preferences are hidden', () => {
    const items = buildPrimaryNavItems({ showPreferences: false });
    expect(items.map((item) => [item.label, item.href])).toEqual([
      ['Recent', HOME_PATH],
      ['Search', SEARCH_PATH],
      ['Wards', WARD_DIRECTORY_PATH],
    ]);
  });

  it('appends Preferences when the visitor can use it', () => {
    const items = buildPrimaryNavItems({ showPreferences: true });
    expect(items.at(-1)).toMatchObject({ label: 'Preferences', href: PREFERENCES_PATH });
    expect(items).toHaveLength(4);
  });

  it('returns a fresh array so callers cannot mutate the shared list', () => {
    const first = buildPrimaryNavItems({ showPreferences: false });
    first.pop();
    expect(buildPrimaryNavItems({ showPreferences: false })).toHaveLength(3);
  });
});

describe('isNavItemActive', () => {
  it.each([
    ['Recent', '/', true],
    ['Recent', '/search', false],
    ['Recent', '/newsletter/123', false],
    ['Search', '/search', true],
    ['Search', '/search/', true],
    ['Search', '/searching', false],
    ['Wards', '/wards', true],
    ['Wards', '/ward/12', true],
    ['Wards', '/ward/12/', true],
    ['Wards', '/wardrobe', false],
    ['Wards', '/newsletter/123', false],
    ['Preferences', '/preferences', true],
    ['Preferences', '/', false],
  ])('%s is active on %s: %s', (label, pathname, expected) => {
    expect(isNavItemActive(findNavItem(label), pathname)).toBe(expected);
  });

  it('treats an empty path as the home page', () => {
    expect(isNavItemActive(findNavItem('Recent'), '')).toBe(true);
  });

  it('marks no item active on pages outside the primary sections', () => {
    const activeItems = buildPrimaryNavItems({ showPreferences: true }).filter((item) =>
      isNavItemActive(item, '/newsletter/42'),
    );
    expect(activeItems).toEqual([]);
  });
});
