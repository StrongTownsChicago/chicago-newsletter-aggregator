import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock Supabase before importing the library
vi.mock('@supabase/supabase-js', () => ({
  createClient: vi.fn(() => ({
    auth: {
      getSession: vi.fn(),
      onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })),
    },
    from: vi.fn(),
  })),
}));

import { createClient } from '@supabase/supabase-js';
import { createRequestClient, notificationsEnabled, supabase } from '../../lib/supabase';

describe('supabase utilities', () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
  });

  describe('clients', () => {
    it('gives each request its own client, never the shared one', () => {
      const first = createRequestClient();
      expect(createRequestClient()).not.toBe(first);
      expect(first).not.toBe(supabase);
    });

    it('never stores or refreshes a session', () => {
      for (const [, , options] of vi.mocked(createClient).mock.calls) {
        expect(options?.auth).toEqual({ persistSession: false, autoRefreshToken: false });
      }
      expect(vi.mocked(createClient).mock.calls.length).toBeGreaterThan(0);
    });
  });

  describe('notificationsEnabled', () => {
    it('returns true when PUBLIC_ENABLE_NOTIFICATIONS is "true"', () => {
      vi.stubEnv('PUBLIC_ENABLE_NOTIFICATIONS', 'true');
      expect(notificationsEnabled()).toBe(true);
    });

    it('returns false when PUBLIC_ENABLE_NOTIFICATIONS is "false"', () => {
      vi.stubEnv('PUBLIC_ENABLE_NOTIFICATIONS', 'false');
      expect(notificationsEnabled()).toBe(false);
    });

    it('returns false when PUBLIC_ENABLE_NOTIFICATIONS is undefined', () => {
      vi.stubEnv('PUBLIC_ENABLE_NOTIFICATIONS', '');
      expect(notificationsEnabled()).toBe(false);
    });
  });
});
