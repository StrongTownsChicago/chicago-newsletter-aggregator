/// <reference types="astro/client" />

// No top-level imports: they would make this file a module and keep these
// declarations from merging with Astro's global types.

interface ImportMetaEnv {
  /** Unique per build, inlined by astro.config.mjs; versions the page cache. */
  readonly BUILD_ID?: string;
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
