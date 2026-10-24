export const prerender = false;

import type { APIRoute } from "astro";
import wardGlanceData from "../generated/ward-glance.json";
import type { WardGlanceFile } from "../lib/ward-glance";
import {
  SITEMAP_RESPONSE_HEADERS,
  buildSitemapXml,
  buildWardSitemapPages,
} from "../lib/server/sitemap";

// Ward pages are server-rendered, so @astrojs/sitemap cannot discover them.
export const GET: APIRoute = ({ site, url }) =>
  new Response(buildSitemapXml(
    buildWardSitemapPages((wardGlanceData as WardGlanceFile).wards),
    site ?? url.origin), {
    status: 200,
    headers: SITEMAP_RESPONSE_HEADERS,
  });
