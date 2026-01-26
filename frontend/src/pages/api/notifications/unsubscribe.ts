export const prerender = false;
import type { APIRoute } from "astro";
import { jwtVerify } from "jose";
import { supabaseAdmin } from "../../../lib/supabase-admin";

export const POST: APIRoute = async ({ request }) => {
  try {
    const { token, user_id } = await request.json();

    if (!token) {
      return new Response(JSON.stringify({ error: "Token required" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Get secret key
    const secretKeyStr = import.meta.env.UNSUBSCRIBE_SECRET_KEY;
    if (!secretKeyStr) {
      console.error("UNSUBSCRIBE_SECRET_KEY not configured");
      return new Response(JSON.stringify({ error: "Server error" }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      });
    }
    const secretKey = new TextEncoder().encode(secretKeyStr);

    // Validate token
    let payload;
    try {
      const result = await jwtVerify(token, secretKey, {
        algorithms: ["HS256"],
      });
      payload = result.payload;
    } catch {
      return new Response(JSON.stringify({ error: "Invalid or expired token" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (payload.type !== "unsubscribe") {
      return new Response(JSON.stringify({ error: "Invalid token type" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    const tokenUserId = payload.sub;

    if (!tokenUserId) {
        return new Response(JSON.stringify({ error: "Invalid token payload" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    // If user_id was provided, ensure it matches the token
    if (user_id && user_id !== tokenUserId) {
      return new Response(JSON.stringify({ error: "User ID mismatch" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Update notification preferences to disabled using admin client
    const { error } = await supabaseAdmin
      .from("user_profiles")
      .update({
        notification_preferences: {
          enabled: false,
          delivery_frequency: "daily",
        },
      })
      .eq("id", tokenUserId);

    if (error) {
      console.error("Unsubscribe error:", error);
      return new Response(
        JSON.stringify({ error: "Failed to unsubscribe" }),
        {
          status: 500,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    return new Response(JSON.stringify({ success: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    console.error("Unsubscribe error:", error);
    return new Response(JSON.stringify({ error: "Server error" }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
};