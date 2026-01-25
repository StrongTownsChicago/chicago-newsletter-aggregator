import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { Session, AuthError } from '@supabase/supabase-js';

type MockAuthResponse = Promise<{
  data: { session: Partial<Session> | null; user: unknown | null };
  error: Partial<AuthError> | null;
}>;

// Mock Supabase
vi.mock('../../lib/supabase', () => ({
  supabase: {
    auth: {
      signInWithPassword: vi.fn(),
      signUp: vi.fn(),
      signOut: vi.fn(),
    },
  },
  notificationsEnabled: vi.fn(() => true),
}));

import { POST as signinPOST } from '../../pages/api/auth/signin';
import { POST as signupPOST } from '../../pages/api/auth/signup';
import { POST as signoutPOST } from '../../pages/api/auth/signout';
import { createMockContext } from '../helpers';
import { supabase, notificationsEnabled } from '../../lib/supabase';

describe('Auth API Routes', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(notificationsEnabled).mockReturnValue(true);
  });

  describe('POST /api/auth/signin', () => {
    it('redirects to / on successful signin', async () => {
      vi.mocked(supabase.auth.signInWithPassword).mockResolvedValue({
        data: { session: { access_token: 'access', refresh_token: 'refresh' }, user: {} },
        error: null,
      } as MockAuthResponse);

      const context = createMockContext({
        formData: { email: 'test@example.com', password: 'password123' },
      });

      const response = await signinPOST(context);

      expect(response.status).toBe(302);
      expect(response.headers.get('Location')).toBe('/');
      expect(context.cookies.set).toHaveBeenCalledWith('sb-access-token', 'access', expect.any(Object));
      expect(context.cookies.set).toHaveBeenCalledWith('sb-refresh-token', 'refresh', expect.any(Object));
    });

    it('redirects to /login with error on failure', async () => {
      vi.mocked(supabase.auth.signInWithPassword).mockResolvedValue({
        data: { session: null, user: null },
        error: { message: 'Invalid credentials' },
      } as MockAuthResponse);

      const context = createMockContext({
        formData: { email: 'test@example.com', password: 'wrong' },
      });

      const response = await signinPOST(context);

      expect(response.status).toBe(302);
      expect(response.headers.get('Location')).toContain('error=Invalid%20credentials');
    });



    it("returns 404 if notifications are disabled", async () => {
      vi.mocked(notificationsEnabled).mockReturnValue(false);

      const context = createMockContext({
        formData: { email: "test@example.com", password: "password123" },
      });

      const response = await signinPOST(context);
      expect(response.status).toBe(404);
    });
  });

  describe('POST /api/auth/signup', () => {
    it('redirects to /preferences on successful signup with immediate session', async () => {
      vi.mocked(supabase.auth.signUp).mockResolvedValue({
        data: { 
          user: { id: '123' },
          session: { access_token: 'access', refresh_token: 'refresh' } 
        },
        error: null,
      } as MockAuthResponse);

      const context = createMockContext({
        formData: { email: 'test@example.com', password: 'password123' },
      });

      const response = await signupPOST(context);

      expect(response.status).toBe(302);
      expect(response.headers.get('Location')).toBe('/preferences');
      expect(context.cookies.set).toHaveBeenCalledWith('sb-access-token', 'access', expect.any(Object));
    });

    it('redirects with message when email confirmation is required', async () => {
      vi.mocked(supabase.auth.signUp).mockResolvedValue({
        data: { 
          user: { id: '123' },
          session: null 
        },
        error: null,
      } as MockAuthResponse);

      const context = createMockContext({
        formData: { email: "test@example.com", password: "password123" },
      });

      const response = await signupPOST(context);

      expect(response.status).toBe(302);
      expect(response.headers.get("Location")).toContain(
        "message=Check your email",
      );
    });

    it("redirects to /signup with error on validation failure (short password)", async () => {
      const context = createMockContext({
        formData: { email: "test@example.com", password: "123" },
      });

      const response = await signupPOST(context);

      expect(response.status).toBe(302);
      expect(response.headers.get("Location")).toContain(
        "error=Password must be at least 6 characters",
      );
    });
  });

  describe("POST /api/auth/signout", () => {
    it("clears cookies and redirects to /", async () => {
      const context = createMockContext();

      const response = await signoutPOST(context);

      expect(response.status).toBe(302);
      expect(response.headers.get("Location")).toBe("/");
      expect(context.cookies.delete).toHaveBeenCalledWith("sb-access-token", {
        path: "/",
      });
      expect(context.cookies.delete).toHaveBeenCalledWith("sb-refresh-token", {
        path: "/",
      });
    });
  });
});
