export const prerender = false;
import type { APIRoute } from "astro";
import { jwtVerify } from "jose";
import { getSupabaseAdmin } from "../../../lib/server/supabase-admin";
import { readServerSecret } from "../../../lib/server/server-env";
import type { UserProfile } from "../../../lib/supabase";

interface PreferencesRequestBody {
  token?: string;
  user_id?: string;
}

const jsonError = (error: string, status: number) =>
  new Response(JSON.stringify({ error }), {
    status,
    headers: { "Content-Type": "application/json" },
  });

/** The user id an unsubscribe token names, or the error response for a bad token. */
async function userIdFromToken(token: string, locals: App.Locals): Promise<string | Response> {
  const secretKeyStr = readServerSecret(locals, "UNSUBSCRIBE_SECRET_KEY");
  if (!secretKeyStr) {
    console.error("UNSUBSCRIBE_SECRET_KEY not configured");
    return jsonError("Server error", 500);
  }
  const secretKey = new TextEncoder().encode(secretKeyStr);
  try {
    const { payload } = await jwtVerify(token, secretKey, {
      algorithms: ["HS256"],
    });
    if (payload.type !== "unsubscribe") throw new Error("Invalid type");
    return payload.sub as string;
  } catch {
    return jsonError("Invalid token", 400);
  }
}

/** Whose preferences to read: the token's user, else the signed-in user, else an error response. */
async function resolveTargetUserId(body: PreferencesRequestBody, locals: App.Locals): Promise<string | Response> {
  // Strategy 1: Token provided (Unsubscribe flow)
  if (body.token) {
    return userIdFromToken(body.token, locals);
  }
  // Strategy 2: Authenticated Session (Standard flow)
  if (locals.user) {
    // If request asks for a specific user, ensure it matches
    if (body.user_id && body.user_id !== locals.user.id) {
      return jsonError("Unauthorized", 403);
    }
    return locals.user.id;
  }
  // Strategy 3: Just user_id provided without auth (Legacy/Insecure - disable for this sensitive data)
  return jsonError("Authorization required", 401);
}

export const POST: APIRoute = async ({ request, locals }) => {
  try {
    // We expect { token } or { user_id } (if logged in)
    // But for the unsubscribe flow, we rely on the token.
    const body = (await request.json()) as PreferencesRequestBody;
    const targetUserId = await resolveTargetUserId(body, locals);
    if (targetUserId instanceof Response) {
      return targetUserId;
    }

    if (!targetUserId) {
      return jsonError("User not identified", 400);
    }

    // Query user preferences using admin client (to ensure we can read even if RLS is strict for anon)
    const supabaseAdmin = getSupabaseAdmin(locals);
    const { data, error } = await supabaseAdmin
      .from("user_profiles")
      .select("notification_preferences")
      .eq("id", targetUserId)
      .single<{
        notification_preferences: UserProfile["notification_preferences"] | null;
      }>();

    if (error || !data) {
      // Don't reveal 404 vs 403 to anon users, but here we have a token so 404 is fine.
      return new Response(JSON.stringify({ error: "User not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    }

    return new Response(
      JSON.stringify({
        enabled: data.notification_preferences?.enabled ?? true,
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    );
  } catch (error) {
    console.error("Get preferences error:", error);
    return new Response(JSON.stringify({ error: "Server error" }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
};
