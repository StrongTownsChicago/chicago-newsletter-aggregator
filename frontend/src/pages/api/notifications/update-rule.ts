export const prerender = false;
import type { APIRoute } from "astro";
import { notificationsEnabled } from "../../../lib/supabase";
import { formText, formTexts } from "../../../lib/server/form-data";

export const POST: APIRoute = async ({ request, locals, redirect }) => {
  if (!notificationsEnabled()) {
    return new Response("Notifications are disabled", { status: 404 });
  }

  const user = locals.user;

  if (!user) {
    return redirect("/login");
  }

  const formData = await request.formData();
  const ruleId = formText(formData, "rule_id");
  const name = formText(formData, "name");
  let deliveryFrequency =
    formText(formData, "delivery_frequency") || "daily";
  const topics = formTexts(formData, "topics");
  let searchTerm = formText(formData, "search_term")?.trim();
  let wards = formTexts(formData, "wards")
    .map((w) => w.trim())
    .filter((w) => w.length > 0);
  const isActive = formData.get("is_active") === "on";

  if (!ruleId || !name) {
    return redirect("/preferences?error=Rule ID and name are required");
  }

  // Validation: Weekly rules
  if (deliveryFrequency === "weekly") {
    if (topics.length === 0) {
      return redirect(
        "/preferences?error=At least one topic is required for weekly summaries",
      );
    }
    if (wards.length > 0) {
      return redirect(
        "/preferences?error=Ward filters cannot be applied to weekly summaries. Weekly summaries cover citywide activity.",
      );
    }
    // Weekly rules cannot have search terms or ward filters
    searchTerm = undefined;
    wards = [];
  } else {
    // Validation: Daily rules (default)
    deliveryFrequency = "daily"; // Ensure it's exactly 'daily' if not 'weekly'

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

  // Update rule (RLS ensures user can only update their own rules)
  const { error } = await locals.supabase
    .from("notification_rules")
    .update({
      name,
      topics,
      search_term: searchTerm || null,
      ward_numbers: wards.length > 0 ? wards : null,
      is_active: isActive,
      delivery_frequency: deliveryFrequency,
    })
    .eq("id", ruleId)
    .eq("user_id", user.id);

  if (error) {
    return redirect(`/preferences?error=${encodeURIComponent(error.message)}`);
  }

  return redirect("/preferences?message=Rule updated successfully");
};
