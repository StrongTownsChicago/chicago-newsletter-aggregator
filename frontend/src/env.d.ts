/// <reference types="astro/client" />

// No top-level imports: they would make this file a module and keep these
// declarations from merging with Astro's global types.

interface ImportMetaEnv {
  /** Unique per build, inlined by astro.config.mjs; versions the page cache. */
  readonly BUILD_ID?: string;
  readonly PUBLIC_SUPABASE_URL: string;
  readonly PUBLIC_SUPABASE_ANON_KEY: string;
  readonly PUBLIC_ENABLE_NOTIFICATIONS?: string;
  /** Server-only: read through lib/server/server-env.ts, which prefers the Cloudflare runtime env. */
  readonly SUPABASE_SERVICE_KEY?: string;
  readonly UNSUBSCRIBE_SECRET_KEY?: string;
}

declare namespace App {
  interface Locals {
    supabase: import("@supabase/supabase-js").SupabaseClient;
    session: import("@supabase/supabase-js").Session | null;
    user: import("@supabase/supabase-js").User | null;
    /** Cloudflare runtime from the adapter; absent outside Workers (tests). */
    runtime?: import("@astrojs/cloudflare").Runtime["runtime"];
  }
}
