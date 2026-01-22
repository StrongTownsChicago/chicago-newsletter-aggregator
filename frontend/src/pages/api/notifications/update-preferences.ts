export const prerender = false;
import type { APIRoute } from "astro";

export const POST: APIRoute = async ({ request, locals, redirect }) => {
  const user = locals.user;

  if (!user) {
    return redirect("/login");
  }

  const formData = await request.formData();
  const enabled = formData.get("enabled") === "on";

  // Update notification preferences
  const { error } = await locals.supabase
    .from("user_profiles")
    .update({
      notification_preferences: {
        enabled,
        delivery_frequency: "daily", // Fixed for MVP
      },
    })
    .eq("id", user.id);

  if (error) {
    return redirect(`/preferences?error=${encodeURIComponent(error.message)}`);
  }

  return redirect("/preferences?message=Preferences updated successfully");
};
