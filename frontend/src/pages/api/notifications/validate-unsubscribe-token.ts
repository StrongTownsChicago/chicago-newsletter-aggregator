export const prerender = false;
import type { APIRoute } from "astro";
import { jwtVerify } from "jose";

export const POST: APIRoute = async ({ request, locals }) => {
  try {
    const { token } = await request.json();

    if (!token) {
      return new Response(JSON.stringify({ error: "Token required" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Get secret key from Cloudflare runtime environment
    const secretKeyStr = locals.runtime?.env?.UNSUBSCRIBE_SECRET_KEY || import.meta.env.UNSUBSCRIBE_SECRET_KEY;
    if (!secretKeyStr) {
      console.error("UNSUBSCRIBE_SECRET_KEY not configured");
      return new Response(
        JSON.stringify({ error: "Server configuration error" }),
        {
          status: 500,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    // Convert secret string to Uint8Array for jose
    const secretKey = new TextEncoder().encode(secretKeyStr);

    try {
      // Validate token
      const { payload } = await jwtVerify(token, secretKey, {
        algorithms: ["HS256"],
      });

      if (payload.type !== "unsubscribe") {
        return new Response(
          JSON.stringify({ error: "Invalid token type" }),
          {
            status: 400,
            headers: { "Content-Type": "application/json" },
          }
        );
      }

      const userId = payload.sub;

      if (!userId) {
         return new Response(
          JSON.stringify({ error: "Invalid token payload" }),
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

    } catch {
      // Token invalid or expired
      return new Response(
        JSON.stringify({ error: "Invalid or expired token" }),
        {
          status: 400,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

  } catch (error) {
    console.error("Token validation error:", error);
    return new Response(JSON.stringify({ error: "Invalid request" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }
};