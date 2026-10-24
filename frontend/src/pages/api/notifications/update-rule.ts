export const prerender = false;
import type { APIRoute } from "astro";
import { notificationsEnabled } from "../../../lib/supabase";
import { formText } from "../../../lib/server/form-data";
import { readRuleFields } from "../../../lib/server/rule-fields";

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

  if (!ruleId || !name) {
    return redirect("/preferences?error=Rule ID and name are required");
  }

  const { fields, error: fieldsError } = readRuleFields(formData);
  if (fieldsError) {
    return redirect(`/preferences?error=${fieldsError}`);
  }

  // RLS ensures user can only update their own rules
  const { error } = await locals.supabase
    .from("notification_rules")
    .update({ name, ...fields })
    .eq("id", ruleId)
    .eq("user_id", user.id);

  if (error) {
    return redirect(`/preferences?error=${encodeURIComponent(error.message)}`);
  }

  return redirect("/preferences?message=Rule updated successfully");
};
