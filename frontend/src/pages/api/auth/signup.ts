export const prerender = false;
import type { APIRoute } from "astro";
import { supabase, notificationsEnabled } from "../../../lib/supabase";

export const POST: APIRoute = async ({ request, cookies, redirect }) => {
  if (!notificationsEnabled()) {
    return new Response("Notifications are disabled", { status: 404 });
  }

  const formData = await request.formData();
  const email = formData.get("email")?.toString();
  const password = formData.get("password")?.toString();

  if (!email || !password) {
    return redirect("/signup?error=Email and password are required");
  }

  if (password.length < 6) {
    return redirect("/signup?error=Password must be at least 6 characters");
  }

  const { data, error } = await supabase.auth.signUp({
    email,
    password,
  });

  if (error) {
    return redirect(`/signup?error=${encodeURIComponent(error.message)}`);
  }

  // Check if email confirmation is required
  if (data.user && !data.session) {
    return redirect("/signup?message=Check your email to confirm your account");
  }

  // If session is created immediately (email confirmation disabled)
  if (data.session) {
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

    return redirect("/preferences");
  }

  return redirect("/login?message=Account created successfully");
};
