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

import { notificationsEnabled } from '../../lib/supabase';

describe('supabase utilities', () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
  });

  describe('notificationsEnabled', () => {
    it('returns true when PUBLIC_ENABLE_NOTIFICATIONS is "true"', () => {
      vi.stubEnv('PUBLIC_ENABLE_NOTIFICATIONS', 'true');
      // @ts-ignore - Vitest stubEnv doesn't always reflect in import.meta.env immediately in all setups
      // but let's see how it behaves here
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
