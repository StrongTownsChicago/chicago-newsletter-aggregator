import type { Json } from "./database.types";

/** What `user_profiles.notification_preferences` holds; written by the preferences and unsubscribe routes. */
export interface NotificationPreferences {
  enabled: boolean;
  delivery_frequency: string;
}

/** Whether a profile's stored preferences have email notifications on. Unset means on, as the column default is. */
export function areNotificationsEnabled(preferences: Json | null | undefined): boolean {
  const isObject = typeof preferences === "object" && preferences !== null && !Array.isArray(preferences);
  return !(isObject && preferences.enabled === false);
}
