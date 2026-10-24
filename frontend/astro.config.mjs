// @ts-check
import { defineConfig } from "astro/config";
import tailwindcss from "@tailwindcss/vite";
import cloudflare from "@astrojs/cloudflare";
import sitemap from "@astrojs/sitemap";

const SITE_URL = "https://chicago-newsletter-aggregator.open-advocacy.com";

// Account, token-driven, and local-only pages that should not appear in search results.
// Keep in sync with the Disallow rules in public/robots.txt.
const NON_INDEXABLE_PATHS = ["/preferences", "/unsubscribe", "/login", "/signup"];

// Versions the edge page cache (src/lib/server/page-cache.ts) so each deploy, including
// a redeploy of the same commit, starts empty. Cloudflare Pages sets the commit.
const BUILD_ID = `${process.env.CF_PAGES_COMMIT_SHA || "local"}-${Date.now()}`;

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
  // Prerendered pages are written as `reports/2026-09.html` rather than
  // `reports/2026-09/index.html`: Cloudflare Pages serves the former at the
  // slash-free URL that canonicals and the sitemap use, but redirects the
  // latter to a trailing-slash URL.
  build: { format: "file" },
  // The dev toolbar configures itself with an inline script, which the
  // Content-Security-Policy (src/lib/content-security-policy.ts) blocks.
  devToolbar: { enabled: false },
  // The adapter excludes `/reports/*` from the worker but not the prerendered
  // index at `/reports` itself, so serve it as a static file too.
  adapter: cloudflare({ routes: { extend: { exclude: [{ pattern: "/reports" }] } } }),
  integrations: [
    sitemap({
      filter: isIndexablePage,
      serialize: (item) => ({ ...item, url: stripTrailingSlash(item.url) }),
      // Newsletter and ward pages are server-rendered, so they are listed by their own endpoints.
      customSitemaps: [
        `${SITE_URL}/sitemap-newsletters.xml`,
        `${SITE_URL}/sitemap-wards.xml`,
      ],
    }),
  ],
  vite: {
    plugins: [tailwindcss()],
    // Never inline scripts: the Content-Security-Policy (src/lib/content-security-policy.ts)
    // allows only script files. Other assets keep Vite's default limit.
    build: {
      assetsInlineLimit: (/** @type {string} */ filePath) => (filePath.endsWith(".js") ? false : undefined),
    },
    define: {
      "import.meta.env.BUILD_ID": JSON.stringify(BUILD_ID),
    },
  },
});
