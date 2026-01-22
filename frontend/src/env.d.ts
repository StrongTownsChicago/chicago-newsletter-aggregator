/// <reference types="astro/client" />

import type { SupabaseClient, Session, User } from "@supabase/supabase-js";

declare namespace App {
  interface Locals {
    supabase: SupabaseClient;
    session: Session | null;
    user: User | null;
  }
}
