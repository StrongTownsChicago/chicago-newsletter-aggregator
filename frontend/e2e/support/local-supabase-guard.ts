// Refuses any Supabase URL or key that isn't the local stack's. frontend/.env
// points at production, so the local-database e2e config checks every value it
// hands the dev server here before starting it. Mirrors
// backend/tests/db_integration/local_guard.py.

const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '[::1]']);

/** Issuer of the demo JWTs `supabase start` prints; hosted keys name their project in `ref`. */
const LOCAL_KEY_ISSUER = 'supabase-demo';

export class NotLocalDatabaseError extends Error {
  override name = 'NotLocalDatabaseError';
}

export function assertLocalSupabaseUrl(url: string): void {
  let host: string;
  try {
    host = new URL(url).hostname;
  } catch {
    throw new NotLocalDatabaseError(`unparseable Supabase URL: ${JSON.stringify(url)}`);
  }
  if (!LOOPBACK_HOSTS.has(host)) {
    throw new NotLocalDatabaseError(`Supabase host ${JSON.stringify(host)} is not local`);
  }
}

function readJwtClaims(key: string): Record<string, unknown> {
  const parts = key.split('.');
  if (parts.length !== 3) {
    throw new NotLocalDatabaseError("key is not a JWT; use the stack's ANON_KEY or SERVICE_ROLE_KEY");
  }
  let claims: unknown;
  try {
    claims = JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8'));
  } catch {
    throw new NotLocalDatabaseError("key's JWT payload is unreadable");
  }
  if (typeof claims !== 'object' || claims === null || Array.isArray(claims)) {
    throw new NotLocalDatabaseError("key's JWT payload is not an object");
  }
  return claims as Record<string, unknown>;
}

export function assertLocalSupabaseKey(key: string): void {
  const claims = readJwtClaims(key);
  if ('ref' in claims) {
    throw new NotLocalDatabaseError(`key belongs to hosted project ${JSON.stringify(claims.ref)}`);
  }
  if (claims.iss !== LOCAL_KEY_ISSUER) {
    throw new NotLocalDatabaseError(`key issuer ${JSON.stringify(claims.iss)} is not the local stack's`);
  }
}
