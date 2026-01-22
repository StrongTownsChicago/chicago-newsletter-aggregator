export const prerender = false;
import type { APIRoute } from "astro";

export const POST: APIRoute = async ({ request, locals, redirect }) => {
  const user = locals.user;

  if (!user) {
    return redirect("/login");
  }

  const formData = await request.formData();
  const name = formData.get("name")?.toString();
  const topics = formData.getAll("topics").map((t) => t.toString());
  const isActive = formData.get("is_active") === "on";

  if (!name || topics.length === 0) {
    return redirect(
      "/preferences?error=Rule name and at least one topic are required",
    );
  }

  // Check rule limit (max 5 rules per user)
  const { count, error: countError } = await locals.supabase
    .from("notification_rules")
    .select("*", { count: "exact", head: true })
    .eq("user_id", user.id);

  if (countError) {
    return redirect(
      `/preferences?error=${encodeURIComponent(countError.message)}`,
    );
  }

  if (count !== null && count >= 5) {
    return redirect("/preferences?error=Maximum 5 rules allowed per user");
  }

  // Create rule
  const { error } = await locals.supabase.from("notification_rules").insert({
    user_id: user.id,
    name,
    topics,
    is_active: isActive,
  });

  if (error) {
    return redirect(`/preferences?error=${encodeURIComponent(error.message)}`);
  }

  return redirect("/preferences?message=Rule created successfully");
};
