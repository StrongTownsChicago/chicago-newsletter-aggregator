export const prerender = false;
import type { APIRoute } from "astro";
import { validateUnsubscribeToken } from "../../../lib/unsubscribe-tokens";

export const POST: APIRoute = async ({ request }) => {
  try {
    const { token } = await request.json();

    if (!token) {
      return new Response(JSON.stringify({ error: "Token required" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Get secret key from environment
    const secretKey = import.meta.env.UNSUBSCRIBE_SECRET_KEY;
    if (!secretKey) {
      console.error("UNSUBSCRIBE_SECRET_KEY not configured");
      return new Response(
        JSON.stringify({ error: "Server configuration error" }),
        {
          status: 500,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    // Validate token
    const userId = validateUnsubscribeToken(token, secretKey);

    if (!userId) {
      return new Response(
        JSON.stringify({ error: "Invalid or expired token" }),
        {
          status: 400,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    return new Response(JSON.stringify({ user_id: userId }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    console.error("Token validation error:", error);
    return new Response(JSON.stringify({ error: "Invalid request" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }
};
