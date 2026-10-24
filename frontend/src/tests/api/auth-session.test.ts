import { describe, it, expect, vi, beforeEach } from "vitest";
import type { AuthResponse, Session, User } from "@supabase/supabase-js";

vi.mock("../../lib/supabase", () => ({
  supabase: { auth: { signInWithPassword: vi.fn(), signUp: vi.fn() } },
  notificationsEnabled: vi.fn(() => true),
}));

import { POST as signinPOST } from "../../pages/api/auth/signin";
import { POST as signupPOST } from "../../pages/api/auth/signup";
import { POST as signoutPOST } from "../../pages/api/auth/signout";
import { createMockContext } from "../helpers";
import { supabase, notificationsEnabled } from "../../lib/supabase";
import { WELCOME_PATH } from "../../lib/onboarding";

const user = { id: "123" } as User;
const session = { access_token: "access", refresh_token: "refresh", user } as Session;
const credentials = { email: "test@example.com", password: "password123" };

// Typed as whichever auth response the mock expects (sign-in and sign-up differ).
const authResult = <AuthResult>(data: { user: User | null; session: Session | null }) =>
  ({ data, error: null }) as AuthResult;

const DAY_SECONDS = 60 * 60 * 24;
// Session cookies must stay out of reach of page scripts and cross-site requests.
const sessionCookie = (maxAge: number) => ({
  path: "/",
  httpOnly: true,
  secure: import.meta.env.PROD,
  sameSite: "lax",
  maxAge,
});

const location = (response: Response) =>
  new URL(response.headers.get("Location")!, "http://localhost");

describe("auth session routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(notificationsEnabled).mockReturnValue(true);
  });

  describe("cookie flags", () => {
    it.each([
      ["signin", signinPOST, () => vi.mocked(supabase.auth.signInWithPassword)],
      ["signup", signupPOST, () => vi.mocked(supabase.auth.signUp)],
    ] as const)("%s sets httpOnly, lax, site-wide session cookies", async (_name, route, auth) => {
      auth().mockResolvedValue(authResult({ user, session }));
      const context = createMockContext({ formData: credentials });

      await route(context);

      expect(context.cookies.set).toHaveBeenCalledWith(
        "sb-access-token",
        "access",
        sessionCookie(7 * DAY_SECONDS),
      );
      expect(context.cookies.set).toHaveBeenCalledWith(
        "sb-refresh-token",
        "refresh",
        sessionCookie(30 * DAY_SECONDS),
      );
    });
  });

  describe("POST /api/auth/signin", () => {
    it("passes the submitted credentials to Supabase", async () => {
      vi.mocked(supabase.auth.signInWithPassword).mockResolvedValue(
        authResult({ user, session }),
      );

      await signinPOST(createMockContext({ formData: credentials }));

      expect(supabase.auth.signInWithPassword).toHaveBeenCalledWith(credentials);
    });

    it("fails without cookies when Supabase returns no session", async () => {
      vi.mocked(supabase.auth.signInWithPassword).mockResolvedValue(
        authResult({ user: null, session: null }),
      );
      const context = createMockContext({ formData: credentials });

      const response = await signinPOST(context);

      expect(location(response).pathname).toBe("/login");
      expect(location(response).searchParams.get("error")).toBe("Failed to sign in");
      expect(context.cookies.set).not.toHaveBeenCalled();
    });

    it("leaves the default next path out of the retry URL", async () => {
      const response = await signinPOST(
        createMockContext({ formData: { email: "test@example.com" } }),
      );

      expect(location(response).searchParams.has("next")).toBe(false);
    });
  });

  describe("POST /api/auth/signup", () => {
    it("accepts a password of exactly 6 characters", async () => {
      vi.mocked(supabase.auth.signUp).mockResolvedValue(authResult({ user, session: null }));

      await signupPOST(
        createMockContext({ formData: { email: "test@example.com", password: "123456" } }),
      );

      expect(supabase.auth.signUp).toHaveBeenCalled();
    });

    it("returns the Supabase error to the signup form", async () => {
      vi.mocked(supabase.auth.signUp).mockResolvedValue({
        data: { user: null, session: null },
        error: { message: "User already registered" },
      } as AuthResponse);

      const response = await signupPOST(createMockContext({ formData: credentials }));

      expect(location(response).pathname).toBe("/signup");
      expect(location(response).searchParams.get("error")).toBe("User already registered");
    });

    it("sends a signup with neither user nor session to login without cookies", async () => {
      vi.mocked(supabase.auth.signUp).mockResolvedValue(authResult({ user: null, session: null }));
      const context = createMockContext({ formData: credentials });

      const response = await signupPOST(context);

      expect(location(response).pathname).toBe("/login");
      expect(location(response).searchParams.get("message")).toBe(
        "Account created successfully",
      );
      expect(context.cookies.set).not.toHaveBeenCalled();
    });

    it("asks a user awaiting confirmation to check their email", async () => {
      vi.mocked(supabase.auth.signUp).mockResolvedValue(authResult({ user, session: null }));

      const response = await signupPOST(createMockContext({ formData: credentials }));

      expect(location(response).pathname).toBe("/signup");
      expect(response.headers.get("Location")).not.toBe(WELCOME_PATH);
    });
  });

  describe("when notifications are disabled", () => {
    it.each([
      ["signup", signupPOST],
      ["signout", signoutPOST],
    ] as const)("%s returns 404 without touching auth", async (_name, route) => {
      vi.mocked(notificationsEnabled).mockReturnValue(false);
      const context = createMockContext({ formData: credentials });

      const response = await route(context);

      expect(response.status).toBe(404);
      expect(supabase.auth.signUp).not.toHaveBeenCalled();
      expect(context.cookies.delete).not.toHaveBeenCalled();
    });
  });
});
