// Before the run: check the local stack answers, reset it to supabase/seed.sql,
// and prove the dev server reads it, with the anon and the service key, rather
// than the database and secrets in frontend/.env.
import { execSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import type { FullConfig } from '@playwright/test';
import { FEATURED_NEWSLETTER, UNSUBSCRIBER } from '../fixtures/db/facts';
import { REPO_ROOT, START_STACK_HINT, readLocalSupabaseEnv } from './local-supabase-env';
import { mintUnsubscribeToken } from './unsubscribe-token';

/** Written by `supabase link`, which points `--linked` commands at a hosted project. */
const LINKED_PROJECT_FILE = path.join(REPO_ROOT, 'supabase', '.temp', 'project-ref');

/** `db reset` restarts the API containers; allow them this long to come back. */
const STACK_READY_TIMEOUT_MS = 60_000;
const STACK_POLL_INTERVAL_MS = 1_000;

async function stackAnswers(apiUrl: string, anonKey: string): Promise<boolean> {
  try {
    const response = await fetch(`${apiUrl}/rest/v1/`, { headers: { apikey: anonKey } });
    return response.ok;
  } catch {
    return false;
  }
}

async function waitForStack(apiUrl: string, anonKey: string, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (!(await stackAnswers(apiUrl, anonKey))) {
    if (Date.now() >= deadline) {
      throw new Error(`The local Supabase API at ${apiUrl} is not answering. ${START_STACK_HINT}`);
    }
    await new Promise((resolve) => setTimeout(resolve, STACK_POLL_INTERVAL_MS));
  }
}

function resetDatabaseToSeed(): void {
  if (existsSync(LINKED_PROJECT_FILE)) {
    throw new Error(`Refusing to reset: this checkout is linked to a hosted project (${LINKED_PROJECT_FILE}).`);
  }
  try {
    execSync(`npx supabase db reset --local --workdir "${REPO_ROOT}"`, { stdio: 'pipe' });
  } catch (error) {
    const stderr = (error as { stderr?: Buffer }).stderr?.toString() ?? '';
    throw new Error(`Resetting the local database to the seed failed:\n${stderr}`);
  }
}

/** Fails unless the dev server renders a newsletter that exists only in the seed. */
async function assertServerReadsSeed(baseURL: string): Promise<void> {
  const response = await fetch(`${baseURL}/newsletter/${FEATURED_NEWSLETTER.id}`);
  const html = await response.text();
  if (response.status !== 200 || !html.includes(FEATURED_NEWSLETTER.subject)) {
    throw new Error(
      `The dev server did not render the seeded newsletter (HTTP ${response.status}), so it is not reading the local database. ` +
        'Check that frontend/.env is not overriding the Supabase settings in playwright.config.ts.',
    );
  }
}

/**
 * Fails unless the server's service-key client reads a seeded profile, which
 * needs both the test unsubscribe secret and the local service key.
 */
async function assertServerSecretsAreLocal(baseURL: string): Promise<void> {
  const response = await fetch(`${baseURL}/api/notifications/get-user-preferences`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: await mintUnsubscribeToken(UNSUBSCRIBER.id) }),
  });
  if (response.status !== 200) {
    throw new Error(
      `The dev server could not read a seeded profile with its service key (HTTP ${response.status}), so its ` +
        'server secrets are not the ones playwright.config.ts sets. Check that frontend/.env is not overriding them.',
    );
  }
}

export default async function globalSetup(config: FullConfig): Promise<void> {
  const { apiUrl, anonKey } = readLocalSupabaseEnv();
  await waitForStack(apiUrl, anonKey, 0);
  resetDatabaseToSeed();
  await waitForStack(apiUrl, anonKey, STACK_READY_TIMEOUT_MS);
  const baseURL = config.projects[0]?.use.baseURL;
  if (!baseURL) throw new Error('playwright.config.ts sets no baseURL');
  await assertServerReadsSeed(baseURL);
  await assertServerSecretsAreLocal(baseURL);
}
