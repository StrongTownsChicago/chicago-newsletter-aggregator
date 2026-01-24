export const prerender = false;
import type { APIRoute } from "astro";
import { notificationsEnabled } from "../../../lib/supabase";

export const POST: APIRoute = async ({ cookies, redirect }) => {
  if (!notificationsEnabled()) {
    return new Response("Notifications are disabled", { status: 404 });
  }

  // Clear session cookies
  cookies.delete("sb-access-token", { path: "/" });
  cookies.delete("sb-refresh-token", { path: "/" });

  return redirect("/");
};
