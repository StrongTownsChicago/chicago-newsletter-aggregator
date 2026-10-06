// Placeholder origin used only to parse relative paths; never exposed to users.
const PARSE_BASE = "http://redirect.invalid";

// ASCII control characters, which URL parsing silently strips (e.g. tabs, newlines).
const CONTROL_CHARACTERS = /[\u0000-\u001F\u007F]/;

// Paths a browser would treat as protocol-relative, i.e. pointing at another host.
const isProtocolRelative = (path: string) =>
  path.startsWith("//") || path.startsWith("/\\");

/**
 * Returns `candidate` if it is a same-origin relative path, otherwise `fallback`.
 * Guards post-login redirects against open-redirect attacks such as
 * `//evil.com`, `/\evil.com`, absolute URLs, and dot-segment tricks like
 * `/.//evil.com` that only become protocol-relative after normalization.
 */
export function getSafeRedirectPath(
  candidate: string | null | undefined,
  fallback: string,
): string {
  if (
    !candidate ||
    !candidate.startsWith("/") ||
    isProtocolRelative(candidate) ||
    CONTROL_CHARACTERS.test(candidate)
  ) {
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

  // Validate the normalized output too: it is what ends up in the Location header.
  const normalizedPath = `${parsed.pathname}${parsed.search}${parsed.hash}`;
  if (isProtocolRelative(normalizedPath)) {
    return fallback;
  }

  return normalizedPath;
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
