export const prerender = false;
import type { APIRoute } from "astro";
import { jwtVerify } from "jose";
import { getSupabaseAdmin } from "../../../lib/supabase-admin";

export const POST: APIRoute = async ({ request, locals }) => {
  try {
    // We expect { token } or { user_id } (if logged in)
    // But for the unsubscribe flow, we rely on the token.
    const body = await request.json();
    const token = body.token;
    const requestUserId = body.user_id;

    let targetUserId: string | null = null;

    // Strategy 1: Token provided (Unsubscribe flow)
    if (token) {
      const secretKeyStr = locals.runtime?.env?.UNSUBSCRIBE_SECRET_KEY || import.meta.env.UNSUBSCRIBE_SECRET_KEY;
      if (!secretKeyStr) {
        console.error("UNSUBSCRIBE_SECRET_KEY not configured");
        return new Response(JSON.stringify({ error: "Server error" }), {
          status: 500,
        });
      }
      const secretKey = new TextEncoder().encode(secretKeyStr);
      try {
        const { payload } = await jwtVerify(token, secretKey, {
          algorithms: ["HS256"],
        });
        if (payload.type !== "unsubscribe") throw new Error("Invalid type");
        targetUserId = payload.sub as string;
      } catch {
        return new Response(JSON.stringify({ error: "Invalid token" }), {
          status: 400,
        });
      }
    }
    // Strategy 2: Authenticated Session (Standard flow)
    else if (locals.user) {
      targetUserId = locals.user.id;
      // If request asks for a specific user, ensure it matches
      if (requestUserId && requestUserId !== targetUserId) {
        return new Response(JSON.stringify({ error: "Unauthorized" }), {
          status: 403,
        });
      }
    }
    // Strategy 3: Just user_id provided without auth (Legacy/Insecure - disable for this sensitive data)
    else {
      return new Response(JSON.stringify({ error: "Authorization required" }), {
        status: 401,
      });
    }

    if (!targetUserId) {
      return new Response(JSON.stringify({ error: "User not identified" }), {
        status: 400,
      });
    }

    // Query user preferences using admin client (to ensure we can read even if RLS is strict for anon)
    const supabaseAdmin = getSupabaseAdmin(locals);
    const { data, error } = await supabaseAdmin
      .from("user_profiles")
      .select("notification_preferences")
      .eq("id", targetUserId)
      .single();

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
