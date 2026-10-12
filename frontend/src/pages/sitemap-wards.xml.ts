export const prerender = false;

import type { APIRoute } from "astro";
import {
  SITEMAP_RESPONSE_HEADERS,
  buildSitemapXml,
  buildWardSitemapPages,
} from "../lib/sitemap";

// Ward pages are server-rendered, so @astrojs/sitemap cannot discover them.
export const GET: APIRoute = ({ site, url }) =>
  new Response(buildSitemapXml(buildWardSitemapPages(), site ?? url.origin), {
    status: 200,
    headers: SITEMAP_RESPONSE_HEADERS,
  });
