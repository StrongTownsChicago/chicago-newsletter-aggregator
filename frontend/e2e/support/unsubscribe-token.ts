// Unsubscribe links as the digest emails carry them: an HS256 JWT with the
// user id in `sub` and `type: "unsubscribe"` (backend/notifications/unsubscribe_tokens.py).
import { SignJWT } from 'jose';

/** The dev server's UNSUBSCRIBE_SECRET_KEY (playwright.config.ts). */
export const E2E_UNSUBSCRIBE_SECRET_KEY = 'local-e2e-unsubscribe-secret';

export function mintUnsubscribeToken(userId: string, secret = E2E_UNSUBSCRIBE_SECRET_KEY): Promise<string> {
  return new SignJWT({ type: 'unsubscribe' })
    .setProtectedHeader({ alg: 'HS256' })
    .setSubject(userId)
    .setExpirationTime('1h')
    .sign(new TextEncoder().encode(secret));
}
