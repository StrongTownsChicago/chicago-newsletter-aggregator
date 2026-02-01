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
  const topics = formData.getAll("topics").map((t) => t.toString());
  let searchTerm = formData.get("search_term")?.toString().trim();
  let wards = formData
    .getAll("wards")
    .map((w) => w.toString().trim())
    .filter((w) => w.length > 0);
  const isActive = formData.get("is_active") === "on";

  if (!name) {
    return redirect("/preferences?error=Rule name is required");
  }

  // Validation: Weekly rules cannot have ward filters
  if (deliveryFrequency === "weekly" && wards.length > 0) {
    return redirect(
      "/preferences?error=Ward filters cannot be applied to weekly summaries. Weekly summaries cover citywide activity.",
    );
  }

  // Validation: Weekly rules must have topics
  if (deliveryFrequency === "weekly") {
    if (topics.length === 0) {
      return redirect(
        "/preferences?error=At least one topic is required for weekly summaries",
      );
    }
    // Weekly rules cannot have search terms
    searchTerm = undefined;
    // Clear any ward filters (belt-and-suspenders)
    wards = [];
  }

  // Validation: Daily rules must have at least search term or topics
  if (deliveryFrequency === "daily") {
    if (!searchTerm && topics.length === 0) {
      return redirect(
        "/preferences?error=Please specify at least one topic or search phrase",
      );
    }
    if (searchTerm && searchTerm.length > 100) {
      return redirect(
        "/preferences?error=Search phrase must be under 100 characters",
      );
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
    delivery_frequency: deliveryFrequency,
  });

  if (error) {
    return redirect(`/preferences?error=${encodeURIComponent(error.message)}`);
  }

  return redirect("/preferences?message=Rule created successfully");
};
