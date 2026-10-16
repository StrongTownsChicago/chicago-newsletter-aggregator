import { createClient } from "@supabase/supabase-js";
import { readServerSecret } from "./server-env";

// SERVER-SIDE ONLY: Do not import this in .astro files or client-side components
// unless inside a server-only block (frontmatter).

if (!import.meta.env.SSR) {
  throw new Error(
    "supabase-admin.ts: Security Error - This module can only be imported on the server.",
  );
}

// Factory function for creating admin client (supports both dev and Cloudflare runtime)
export function getSupabaseAdmin(
  locals?: Pick<App.Locals, "runtime">,
) {
  const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL;

  const serviceRoleKey = readServerSecret(locals, "SUPABASE_SERVICE_KEY");

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
