import { createClient } from "@supabase/supabase-js";
import type { SupabaseClient } from "@supabase/supabase-js";

// SERVER-SIDE ONLY: Do not import this in .astro files or client-side components
// unless inside a server-only block (frontmatter).

if (!import.meta.env.SSR) {
  throw new Error(
    "supabase-admin.ts: Security Error - This module can only be imported on the server.",
  );
}

// Factory function for creating admin client (supports both dev and Cloudflare runtime)
export function getSupabaseAdmin(locals?: {
  runtime?: { env?: Record<string, string> };
}): SupabaseClient {
  const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL;

  // Try to get service role key from Cloudflare runtime env first, then fall back to import.meta.env for local dev
  const serviceRoleKey =
    locals?.runtime?.env?.SUPABASE_SERVICE_ROLE_KEY ||
    import.meta.env.SUPABASE_SERVICE_ROLE_KEY;

  if (!supabaseUrl || !serviceRoleKey) {
    throw new Error("Missing Supabase URL or Service Role Key");
  }

  return createClient(supabaseUrl, serviceRoleKey, {
    auth: {
      autoRefreshToken: false,
      persistSession: false,
    },
  });
}
