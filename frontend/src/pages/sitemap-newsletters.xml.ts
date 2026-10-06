export const prerender = false;

import type { APIRoute } from "astro";
import { supabase } from "../lib/supabase";
import {
  buildNewsletterSitemapXml,
  fetchNewsletterSitemapEntries,
} from "../lib/sitemap";

const CACHE_MAX_AGE_SECONDS = 60 * 60;

export const GET: APIRoute = async ({ site, url }) => {
  try {
    const entries = await fetchNewsletterSitemapEntries(supabase);
    const xml = buildNewsletterSitemapXml(entries, site ?? url.origin);

    return new Response(xml, {
      status: 200,
      headers: {
        "Content-Type": "application/xml; charset=utf-8",
        "Cache-Control": `public, max-age=${CACHE_MAX_AGE_SECONDS}`,
      },
    });
  } catch (error) {
    console.error("Error generating newsletter sitemap:", error);
    return new Response("Failed to generate sitemap", { status: 500 });
  }
};
