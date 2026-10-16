export const prerender = false;

import type { APIRoute } from "astro";
import { supabase } from "../lib/supabase";
import {
  SITEMAP_RESPONSE_HEADERS,
  buildNewsletterSitemapXml,
  fetchNewsletterSitemapEntries,
} from "../lib/server/sitemap";

export const GET: APIRoute = async ({ site, url }) => {
  try {
    const entries = await fetchNewsletterSitemapEntries(supabase);
    const xml = buildNewsletterSitemapXml(entries, site ?? url.origin);

    return new Response(xml, {
      status: 200,
      headers: SITEMAP_RESPONSE_HEADERS,
    });
  } catch (error) {
    console.error("Error generating newsletter sitemap:", error);
    return new Response("Failed to generate sitemap", { status: 500 });
  }
};
