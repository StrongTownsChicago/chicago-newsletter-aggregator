export const prerender = false;
import type { APIRoute } from "astro";
import { notificationsEnabled } from "../../../lib/supabase";

export const POST: APIRoute = async ({ request, locals, redirect }) => {
  if (!notificationsEnabled()) {
    return new Response("Notifications are disabled", { status: 404 });
  }

  const user = locals.user;

  if (!user) {
    return redirect("/login");
  }

  const formData = await request.formData();
  const name = formData.get("name")?.toString();
  const ruleType = formData.get("rule_type")?.toString() || "search";
  let topics = formData.getAll("topics").map((t) => t.toString());
  let searchTerm = formData.get("search_term")?.toString().trim();
  const wards = formData
    .getAll("wards")
    .map((w) => w.toString().trim())
    .filter((w) => w.length > 0);
  const isActive = formData.get("is_active") === "on";

  if (!name) {
    return redirect("/preferences?error=Rule name is required");
  }

  // Handle Mutual Exclusivity based on rule type
  if (ruleType === "search") {
    // Search Mode: Clear topics, require search term
    topics = [];
    if (!searchTerm) {
      return redirect("/preferences?error=Search phrase is required");
    }
    if (searchTerm.length > 100) {
      return redirect(
        "/preferences?error=Search phrase must be under 100 characters",
      );
    }
  } else {
    // Topic Mode: Clear search term, require topics
    searchTerm = undefined;
    if (topics.length === 0) {
      return redirect("/preferences?error=At least one topic is required");
    }
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
    search_term: searchTerm || null,
    ward_numbers: wards.length > 0 ? wards : null,
    is_active: isActive,
  });

  if (error) {
    return redirect(`/preferences?error=${encodeURIComponent(error.message)}`);
  }

  return redirect("/preferences?message=Rule created successfully");
};
