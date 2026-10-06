// @ts-check
import { defineConfig } from "astro/config";
import tailwindcss from "@tailwindcss/vite";
import cloudflare from "@astrojs/cloudflare";
import sitemap from "@astrojs/sitemap";

const SITE_URL = "https://chicago-newsletter-aggregator.open-advocacy.com";

// Account and token-driven pages that should not appear in search results.
// Keep in sync with the Disallow rules in public/robots.txt.
const NON_INDEXABLE_PATHS = ["/preferences", "/unsubscribe", "/login", "/signup"];

const isIndexablePage = (/** @type {string} */ page) => {
  const { pathname } = new URL(page);
  return !NON_INDEXABLE_PATHS.some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  );
};

// Match the canonical URLs emitted by Layout.astro, which omit trailing slashes.
const stripTrailingSlash = (/** @type {string} */ page) => {
  const url = new URL(page);
  if (url.pathname.length > 1) {
    url.pathname = url.pathname.replace(/\/+$/, "");
  }
  return url.href;
};

export default defineConfig({
  site: SITE_URL,
  output: "static",
  adapter: cloudflare(),
  integrations: [
    sitemap({
      filter: isIndexablePage,
      serialize: (item) => ({ ...item, url: stripTrailingSlash(item.url) }),
      // Newsletter detail pages are server-rendered, so they are listed by a dynamic endpoint.
      customSitemaps: [`${SITE_URL}/sitemap-newsletters.xml`],
    }),
  ],
  vite: {
    plugins: [tailwindcss()],
  },
});
