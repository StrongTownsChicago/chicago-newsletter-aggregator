import { createClient } from "@supabase/supabase-js";

// SERVER-SIDE ONLY: Do not import this in .astro files or client-side components
// unless inside a server-only block (frontmatter).

if (!import.meta.env.SSR) {
  throw new Error(
    "supabase-admin.ts: Security Error - This module can only be imported on the server."
  );
}

const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL;
const serviceRoleKey = import.meta.env.SUPABASE_SERVICE_ROLE_KEY;

if (!supabaseUrl || !serviceRoleKey) {
  // This error will likely happen at build time if this file is imported on the client,
  // or at runtime on the server if the env var is missing.
  // We throw a clear error to prevent "undefined" issues later.
  throw new Error("Missing Supabase URL or Service Role Key");
}

export const supabaseAdmin = createClient(supabaseUrl, serviceRoleKey, {
  auth: {
    autoRefreshToken: false,
    persistSession: false,
  },
});