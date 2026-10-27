/**
 * The site's Content-Security-Policy, a second line of defense behind the
 * backend's markup sanitizer (backend/ingest/markup_sanitizer.py) for
 * newsletter HTML rendered into our pages.
 *
 * Scripts load only from the site's own files, so astro.config.mjs keeps Astro
 * from inlining small scripts, and from Cloudflare Web Analytics, whose beacon
 * Cloudflare Pages adds to every page in production. Styles allow 'unsafe-inline' for newsletters'
 * inline style attributes, and images may come from any host because
 * newsletters embed their own. Any site may frame our pages, since other sites
 * embed them; session cookies are SameSite=Lax, so a framed page is always
 * signed out and has no account actions to hijack. The middleware sets it on server-rendered
 * pages; public/_headers repeats it for static files (a test keeps the two equal).
 */
const CLOUDFLARE_WEB_ANALYTICS_ORIGIN = "https://static.cloudflareinsights.com";

const DIRECTIVES: Record<string, string[]> = {
  "default-src": ["'self'"],
  "script-src": ["'self'", CLOUDFLARE_WEB_ANALYTICS_ORIGIN],
  "style-src": ["'self'", "'unsafe-inline'"],
  "img-src": ["*", "data:"],
  "font-src": ["'self'"],
  "connect-src": ["'self'"],
  "object-src": ["'none'"],
  "frame-src": ["'none'"],
  "base-uri": ["'self'"],
  "form-action": ["'self'"],
  "frame-ancestors": ["*"],
};

export const CONTENT_SECURITY_POLICY = Object.entries(DIRECTIVES)
  .map(([directive, sources]) => `${directive} ${sources.join(" ")}`)
  .join("; ");

export const CONTENT_SECURITY_POLICY_HEADER = "Content-Security-Policy";
