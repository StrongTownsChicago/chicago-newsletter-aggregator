import { describe, it, expect } from 'vitest';
import {
  CONFIRMED_EMAIL_MESSAGE,
  STARTER_RULE,
  WELCOME_PATH,
  buildEmailConfirmationRedirect,
  shouldShowWelcome,
} from '../../lib/onboarding';
import { getSafeRedirectPath } from '../../lib/redirects';
import { ALL_TOPICS } from '../../lib/topics';

describe('shouldShowWelcome', () => {
  it('shows welcome when the flag is set and the user has no rules', () => {
    expect(shouldShowWelcome(new URLSearchParams('welcome=1'), 0)).toBe(true);
  });

  it('hides welcome once the user has a rule', () => {
    expect(shouldShowWelcome(new URLSearchParams('welcome=1'), 1)).toBe(false);
  });

  it('hides welcome without the flag', () => {
    expect(shouldShowWelcome(new URLSearchParams(''), 0)).toBe(false);
    expect(shouldShowWelcome(new URLSearchParams('welcome=true'), 0)).toBe(false);
  });
});

describe('buildEmailConfirmationRedirect', () => {
  it('sends confirmed users to login with the welcome page as next', () => {
    const url = new URL(buildEmailConfirmationRedirect('https://example.org'));
    expect(url.origin).toBe('https://example.org');
    expect(url.pathname).toBe('/login');
    expect(url.searchParams.get('next')).toBe(WELCOME_PATH);
    expect(url.searchParams.get('message')).toBe(CONFIRMED_EMAIL_MESSAGE);
  });

  it('produces a next value that survives redirect sanitization', () => {
    const url = new URL(buildEmailConfirmationRedirect('http://localhost:4321'));
    expect(getSafeRedirectPath(url.searchParams.get('next'), '/')).toBe(WELCOME_PATH);
  });
});

describe('STARTER_RULE', () => {
  it('is a valid weekly rule (weekly rules require at least one topic)', () => {
    expect(STARTER_RULE.deliveryFrequency).toBe('weekly');
    expect(STARTER_RULE.topics.length).toBeGreaterThan(0);
    expect(STARTER_RULE.name.trim()).not.toBe('');
  });

  it('only uses topics offered in the rule form', () => {
    for (const topic of STARTER_RULE.topics) {
      expect(ALL_TOPICS).toContain(topic);
    }
  });
});
