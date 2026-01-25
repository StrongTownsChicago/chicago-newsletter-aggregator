export const prerender = false;
import type { APIRoute } from "astro";

export const POST: APIRoute = async ({ request, locals }) => {
  try {
    const { user_id } = await request.json();

    if (!user_id) {
      return new Response(JSON.stringify({ error: "User ID required" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Query user preferences using service role (bypass RLS)
    const { data, error } = await locals.supabase
      .from("user_profiles")
      .select("notification_preferences")
      .eq("id", user_id)
      .single();

    if (error || !data) {
      return new Response(JSON.stringify({ error: "User not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    }

    return new Response(
      JSON.stringify({
        enabled: data.notification_preferences?.enabled ?? true,
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }
    );
  } catch (error) {
    console.error("Get preferences error:", error);
    return new Response(JSON.stringify({ error: "Server error" }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
};
