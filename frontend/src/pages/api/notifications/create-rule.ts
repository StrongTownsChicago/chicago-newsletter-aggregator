export const prerender = false;
import type { APIRoute } from "astro";
import { notificationsEnabled } from "../../../lib/supabase";
import { formText } from "../../../lib/server/form-data";
import { readRuleFields } from "../../../lib/server/rule-fields";

const MAX_RULES_PER_USER = 5;

export const POST: APIRoute = async ({ request, locals, redirect }) => {
  if (!notificationsEnabled()) {
    return new Response("Notifications are disabled", { status: 404 });
  }

  const user = locals.user;

  if (!user) {
    return redirect("/login");
  }

  const formData = await request.formData();
  const name = formText(formData, "name");

  if (!name) {
    return redirect("/preferences?error=Rule name is required");
  }

  const { fields, error: fieldsError } = readRuleFields(formData);
  if (fieldsError) {
    return redirect(`/preferences?error=${fieldsError}`);
  }

  const { count, error: countError } = await locals.supabase
    .from("notification_rules")
    .select("*", { count: "exact", head: true })
    .eq("user_id", user.id);

  if (countError) {
    return redirect(
      `/preferences?error=${encodeURIComponent(countError.message)}`,
    );
  }

  if (count !== null && count >= MAX_RULES_PER_USER) {
    return redirect(
      `/preferences?error=Maximum ${MAX_RULES_PER_USER} rules allowed per user`,
    );
  }

  const { error } = await locals.supabase
    .from("notification_rules")
    .insert({ user_id: user.id, name, ...fields });

  if (error) {
    return redirect(`/preferences?error=${encodeURIComponent(error.message)}`);
  }

  return redirect("/preferences?message=Rule created successfully");
};
