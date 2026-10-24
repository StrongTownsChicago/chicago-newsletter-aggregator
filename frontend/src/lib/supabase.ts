import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import type { Database, Tables } from "./database.types";

/** A Supabase client typed with the database schema. */
export type AppSupabaseClient = SupabaseClient<Database>;

const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.PUBLIC_SUPABASE_ANON_KEY;

// Create Supabase client with auth enabled
export const supabase = createClient<Database>(supabaseUrl, supabaseAnonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
  },
});

// Check if notifications are enabled via env var
export const notificationsEnabled = () => {
  return import.meta.env.PUBLIC_ENABLE_NOTIFICATIONS === "true";
};

// Row types come from the generated schema types (`npm run db:types`).
export type Newsletter = Tables<"newsletters">;
export type Source = Tables<"sources">;

export type NotificationRule = Tables<"notification_rules">;
