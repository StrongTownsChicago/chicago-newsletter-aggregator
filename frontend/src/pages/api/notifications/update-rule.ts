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
  const ruleType = formData.get("rule_type")?.toString() || "search";
  let topics = formData.getAll("topics").map((t) => t.toString());
  let searchTerm = formData.get("search_term")?.toString().trim();
  const wards = formData.getAll("wards").map((w) => w.toString().trim()).filter(w => w.length > 0);
  const isActive = formData.get("is_active") === "on";

  if (!ruleId || !name) {
    return redirect("/preferences?error=Rule ID and name are required");
  }

  // Handle Mutual Exclusivity based on rule type
  if (ruleType === "search") {
    // Search Mode: Clear topics, require search term
    topics = [];
    if (!searchTerm) {
      return redirect("/preferences?error=Search phrase is required");
    }
    if (searchTerm.length > 100) {
      return redirect("/preferences?error=Search phrase must be under 100 characters");
    }
  } else {
    // Topic Mode: Clear search term, require topics
    searchTerm = undefined;
    if (topics.length === 0) {
      return redirect("/preferences?error=At least one topic is required");
    }
  }

  // Update rule (RLS ensures user can only update their own rules)
  const { error } = await locals.supabase
    .from("notification_rules")
    .update({
      name,
      topics,
      search_term: searchTerm || null,
      ward_numbers: wards.length > 0 ? wards : null,
      is_active: isActive,
    })
    .eq("id", ruleId)
    .eq("user_id", user.id);

  if (error) {
    return redirect(`/preferences?error=${encodeURIComponent(error.message)}`);
  }

  return redirect("/preferences?message=Rule updated successfully");
};
