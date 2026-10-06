// New-user onboarding: steer freshly confirmed accounts to create their first alert.
// Without at least one rule, a user never receives any notification emails.

export const WELCOME_PATH = "/preferences?welcome=1";

// Neutral wording: Supabase also uses this redirect when confirmation fails
// (e.g. an expired link), so the message must not claim success.
export const CONFIRMED_EMAIL_MESSAGE = "Sign in to set up your first alert.";

export interface StarterRule {
  name: string;
  deliveryFrequency: "daily" | "weekly";
  topics: string[];
}

// Starting state of the rule modal during onboarding. A weekly citywide summary
// is low-volume, but no topics are pre-selected: unwanted subscriptions add
// sending cost, so users should opt in only to topics they care about.
export const STARTER_RULE: StarterRule = {
  name: "Weekly Summary",
  deliveryFrequency: "weekly",
  topics: [],
};

/**
 * The welcome flow only applies to users who have not created any rules yet;
 * revisiting the welcome URL later just shows the normal preferences page.
 */
export function shouldShowWelcome(
  searchParams: URLSearchParams,
  ruleCount: number,
): boolean {
  return searchParams.get("welcome") === "1" && ruleCount === 0;
}

/**
 * Builds the URL Supabase sends users to after they click the confirmation link.
 * The URL must be listed under Auth > URL Configuration > Redirect URLs in
 * Supabase, otherwise Supabase falls back to the project's Site URL.
 */
export function buildEmailConfirmationRedirect(origin: string): string {
  const url = new URL("/login", origin);
  url.searchParams.set("next", WELCOME_PATH);
  url.searchParams.set("message", CONFIRMED_EMAIL_MESSAGE);
  return url.toString();
}
