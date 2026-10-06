// Placeholder origin used only to parse relative paths; never exposed to users.
const PARSE_BASE = "http://redirect.invalid";

/**
 * Returns `candidate` if it is a same-origin relative path, otherwise `fallback`.
 * Guards post-login redirects against open-redirect attacks such as
 * `//evil.com`, `/\evil.com`, or absolute URLs.
 */
export function getSafeRedirectPath(
  candidate: string | null | undefined,
  fallback: string,
): string {
  if (!candidate || !candidate.startsWith("/") || candidate.startsWith("//")) {
    return fallback;
  }

  let parsed: URL;
  try {
    parsed = new URL(candidate, PARSE_BASE);
  } catch {
    return fallback;
  }

  if (parsed.origin !== PARSE_BASE) {
    return fallback;
  }

  return `${parsed.pathname}${parsed.search}${parsed.hash}`;
}

/**
 * Builds a /login URL that carries an error or message while preserving the
 * post-login destination, so a failed attempt doesn't drop the user's `next`.
 */
export function buildLoginUrl(params: {
  error?: string;
  next?: string | null;
}): string {
  const searchParams = new URLSearchParams();
  if (params.error) searchParams.set("error", params.error);
  if (params.next) searchParams.set("next", params.next);
  const query = searchParams.toString();
  return query ? `/login?${query}` : "/login";
}
