export const prerender = false;
import type { APIRoute } from "astro";

export const POST: APIRoute = async ({ request, locals, redirect }) => {
  const user = locals.user;

  if (!user) {
    return redirect("/login");
  }

  const formData = await request.formData();
  const ruleId = formData.get("rule_id")?.toString();
  const name = formData.get("name")?.toString();
  const topics = formData.getAll("topics").map((t) => t.toString());
  const isActive = formData.get("is_active") === "on";

  if (!ruleId || !name || topics.length === 0) {
    return redirect(
      "/preferences?error=Rule ID, name, and at least one topic are required",
    );
  }

  // Update rule (RLS ensures user can only update their own rules)
  const { error } = await locals.supabase
    .from("notification_rules")
    .update({
      name,
      topics,
      is_active: isActive,
    })
    .eq("id", ruleId)
    .eq("user_id", user.id);

  if (error) {
    return redirect(`/preferences?error=${encodeURIComponent(error.message)}`);
  }

  return redirect("/preferences?message=Rule updated successfully");
};
