export const prerender = false;
import type { APIRoute } from "astro";

export const POST: APIRoute = async ({ request, locals, redirect }) => {
  const user = locals.user;

  if (!user) {
    return redirect("/login");
  }

  const formData = await request.formData();
  const ruleId = formData.get("rule_id")?.toString();

  if (!ruleId) {
    return redirect("/preferences?error=Rule ID is required");
  }

  // Delete rule (RLS ensures user can only delete their own rules)
  const { error } = await locals.supabase
    .from("notification_rules")
    .delete()
    .eq("id", ruleId)
    .eq("user_id", user.id);

  if (error) {
    return redirect(`/preferences?error=${encodeURIComponent(error.message)}`);
  }

  return redirect("/preferences?message=Rule deleted successfully");
};
