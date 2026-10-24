export const prerender = false;
import type { APIRoute } from "astro";
import { createRequestClient, notificationsEnabled } from "../../../lib/supabase";
import { buildLoginUrl, getSafeRedirectPath } from "../../../lib/server/redirects";
import { formText } from "../../../lib/server/form-data";

export const POST: APIRoute = async ({ request, cookies, redirect }) => {
  if (!notificationsEnabled()) {
    return new Response("Notifications are disabled", { status: 404 });
  }

  const formData = await request.formData();
  const email = formText(formData, "email");
  const password = formText(formData, "password");
  const next = getSafeRedirectPath(formText(formData, "next"), "/");
  const preservedNext = next === "/" ? null : next;

  if (!email || !password) {
    return redirect(
      buildLoginUrl({ error: "Email and password are required", next: preservedNext }),
    );
  }

  const { data, error } = await createRequestClient().auth.signInWithPassword({
    email,
    password,
  });

  if (error) {
    return redirect(buildLoginUrl({ error: error.message, next: preservedNext }));
  }

  if (data.session) {
    // Set session cookies
    cookies.set("sb-access-token", data.session.access_token, {
      path: "/",
      httpOnly: true,
      secure: import.meta.env.PROD,
      sameSite: "lax",
      maxAge: 60 * 60 * 24 * 7, // 1 week
    });

    cookies.set("sb-refresh-token", data.session.refresh_token, {
      path: "/",
      httpOnly: true,
      secure: import.meta.env.PROD,
      sameSite: "lax",
      maxAge: 60 * 60 * 24 * 30, // 30 days
    });

    return redirect(next);
  }

  return redirect(buildLoginUrl({ error: "Failed to sign in", next: preservedNext }));
};
