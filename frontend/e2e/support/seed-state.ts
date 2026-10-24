// Puts a seeded user's state back before a spec that changes it, so a retried
// test starts where the seed left it. Writes go to the local stack only: the
// settings come from readLocalSupabaseEnv, which runs the local-only guard.
import { readLocalSupabaseEnv } from './local-supabase-env';

/** The seed's notification preferences: the column default from migration 001. */
const SEEDED_NOTIFICATION_PREFERENCES = { enabled: true, delivery_frequency: 'daily' };

export async function restoreSeededNotificationPreferences(userId: string): Promise<void> {
  const { apiUrl, serviceRoleKey } = readLocalSupabaseEnv();
  const response = await fetch(`${apiUrl}/rest/v1/user_profiles?id=eq.${encodeURIComponent(userId)}`, {
    method: 'PATCH',
    headers: {
      apikey: serviceRoleKey,
      Authorization: `Bearer ${serviceRoleKey}`,
      'Content-Type': 'application/json',
      Prefer: 'return=representation',
    },
    body: JSON.stringify({ notification_preferences: SEEDED_NOTIFICATION_PREFERENCES }),
  });
  const updated = (await response.json()) as unknown[];
  if (!response.ok || updated.length !== 1) {
    throw new Error(`Restoring the seeded preferences of user ${userId} failed (HTTP ${response.status}).`);
  }
}
