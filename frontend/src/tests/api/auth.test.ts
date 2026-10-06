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
import { WELCOME_PATH } from '../../lib/onboarding';

const successfulSignIn = () =>
  vi.mocked(supabase.auth.signInWithPassword).mockResolvedValue({
    data: { session: { access_token: 'access', refresh_token: 'refresh' }, user: {} },
    error: null,
  } as MockAuthResponse);

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

    it('redirects to a safe next path on successful signin', async () => {
      successfulSignIn();

      const context = createMockContext({
        formData: { email: 'test@example.com', password: 'password123', next: WELCOME_PATH },
      });

      const response = await signinPOST(context);

      expect(response.headers.get('Location')).toBe(WELCOME_PATH);
    });

    it('ignores an off-site next path and redirects to /', async () => {
      successfulSignIn();

      const context = createMockContext({
        formData: { email: 'test@example.com', password: 'password123', next: '//evil.com' },
      });

      const response = await signinPOST(context);

      expect(response.headers.get('Location')).toBe('/');
    });

    it('preserves next when signin fails so the user can retry', async () => {
      vi.mocked(supabase.auth.signInWithPassword).mockResolvedValue({
        data: { session: null, user: null },
        error: { message: 'Invalid credentials' },
      } as MockAuthResponse);

      const context = createMockContext({
        formData: { email: 'test@example.com', password: 'wrong', next: WELCOME_PATH },
      });

      const response = await signinPOST(context);
      const location = new URL(response.headers.get('Location')!, 'http://localhost');

      expect(location.pathname).toBe('/login');
      expect(location.searchParams.get('error')).toBe('Invalid credentials');
      expect(location.searchParams.get('next')).toBe(WELCOME_PATH);
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
      const location = new URL(response.headers.get('Location')!, 'http://localhost');
      expect(location.searchParams.get('error')).toBe('Invalid credentials');
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
    it('redirects to the welcome page on successful signup with immediate session', async () => {
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
      expect(response.headers.get('Location')).toBe(WELCOME_PATH);
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

    it("asks Supabase to send confirmed users to login with the welcome page as next", async () => {
      vi.mocked(supabase.auth.signUp).mockResolvedValue({
        data: { user: { id: '123' }, session: null },
        error: null,
      } as MockAuthResponse);

      const context = createMockContext({
        formData: { email: "test@example.com", password: "password123" },
      });

      await signupPOST(context);

      const signUpArgs = vi.mocked(supabase.auth.signUp).mock.calls[0][0] as {
        options?: { emailRedirectTo?: string };
      };
      const redirectTo = new URL(signUpArgs.options!.emailRedirectTo!);
      expect(redirectTo.origin).toBe("http://localhost:4321");
      expect(redirectTo.pathname).toBe("/login");
      expect(redirectTo.searchParams.get("next")).toBe(WELCOME_PATH);
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
