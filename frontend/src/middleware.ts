import { defineMiddleware } from "astro:middleware";
import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.PUBLIC_SUPABASE_ANON_KEY;

export const onRequest = defineMiddleware(async (context, next) => {
  // Create a Supabase client for this request
  const supabase = createClient(supabaseUrl, supabaseAnonKey, {
    auth: {
      persistSession: false, // Server-side doesn't persist
      autoRefreshToken: false,
    },
  });

  // Try to restore session from cookies
  const accessToken = context.cookies.get("sb-access-token")?.value;
  const refreshToken = context.cookies.get("sb-refresh-token")?.value;

  if (accessToken && refreshToken) {
    await supabase.auth.setSession({
      access_token: accessToken,
      refresh_token: refreshToken,
    });
  }

  // Inject authenticated Supabase client into context
  context.locals.supabase = supabase;

  // Get current user session
  const {
    data: { session },
  } = await supabase.auth.getSession();

  context.locals.session = session;
  context.locals.user = session?.user ?? null;

  return next();
});
