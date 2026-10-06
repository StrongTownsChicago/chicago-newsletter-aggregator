import { describe, it, expect } from 'vitest';
import { buildLoginUrl, getSafeRedirectPath } from '../../lib/redirects';

describe('getSafeRedirectPath', () => {
  it('keeps encoded slashes as same-origin paths', () => {
    expect(getSafeRedirectPath('/%2F/evil.com', '/')).toBe('/%2F/evil.com');
  });

  it('returns relative paths unchanged, including query and hash', () => {
    expect(getSafeRedirectPath('/preferences?welcome=1', '/')).toBe('/preferences?welcome=1');
    expect(getSafeRedirectPath('/search?q=cta#results', '/')).toBe('/search?q=cta#results');
  });

  it.each([
    ['missing value', null],
    ['undefined value', undefined],
    ['empty string', ''],
    ['absolute URL', 'https://evil.com/phish'],
    ['protocol-relative URL', '//evil.com'],
    ['backslash host trick', '/\\evil.com'],
    ['javascript URL', 'javascript:alert(1)'],
    ['path without leading slash', 'preferences'],
    ['dot segment before double slash', '/.//evil.com'],
    ['parent segment before double slash', '/a/..//evil.com'],
    ['encoded dot segment', '/%2e//evil.com'],
    ['mixed encoded dot segments', '/.%2e//evil.com'],
    ['encoded parent segment', '/%2e%2e//evil.com'],
    ['dot segment before backslash', '/./\\evil.com'],
    ['tab inside dot segment', '/.\t//evil.com'],
    ['dot segment before slash-backslash', '/.//\\evil.com'],
    ['tab after leading slash', '/\t/evil.com'],
    ['newline after leading slash', '/\n/evil.com'],
  ])('falls back for %s', (_label, candidate) => {
    expect(getSafeRedirectPath(candidate, '/')).toBe('/');
  });
});

describe('buildLoginUrl', () => {
  it('returns bare /login with no params', () => {
    expect(buildLoginUrl({})).toBe('/login');
  });

  it('encodes the error and preserves next', () => {
    const url = new URL(buildLoginUrl({ error: 'Invalid credentials', next: '/preferences?welcome=1' }), 'http://localhost');
    expect(url.pathname).toBe('/login');
    expect(url.searchParams.get('error')).toBe('Invalid credentials');
    expect(url.searchParams.get('next')).toBe('/preferences?welcome=1');
  });

  it('omits next when null', () => {
    expect(buildLoginUrl({ error: 'Oops', next: null })).toBe('/login?error=Oops');
  });
});
