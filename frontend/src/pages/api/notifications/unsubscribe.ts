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

    // Update notification preferences to disabled using service role
    const { error } = await locals.supabase
      .from("user_profiles")
      .update({
        notification_preferences: {
          enabled: false,
          delivery_frequency: "daily",
        },
      })
      .eq("id", user_id);

    if (error) {
      console.error("Unsubscribe error:", error);
      return new Response(
        JSON.stringify({ error: "Failed to unsubscribe" }),
        {
          status: 500,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    return new Response(JSON.stringify({ success: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    console.error("Unsubscribe error:", error);
    return new Response(JSON.stringify({ error: "Server error" }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
};
