// The local Supabase stack's URL and demo keys, read from `supabase status`,
// never from frontend/.env (which points at production). Every value passes
// the local-only guard before anything uses it.
import { execSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { assertLocalSupabaseKey, assertLocalSupabaseUrl } from './local-supabase-guard';

export const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..');

export const START_STACK_HINT = 'Start it from frontend/ with `npx supabase start --workdir ..` (needs Docker).';

export interface LocalSupabaseEnv {
  apiUrl: string;
  anonKey: string;
  serviceRoleKey: string;
}

// The config file is loaded again in every test worker; these carry the first
// read to them so `supabase status` runs once per run.
const CACHED_ENV_NAMES = {
  apiUrl: 'E2E_LOCAL_SUPABASE_API_URL',
  anonKey: 'E2E_LOCAL_SUPABASE_ANON_KEY',
  serviceRoleKey: 'E2E_LOCAL_SUPABASE_SERVICE_ROLE_KEY',
} as const satisfies Record<keyof LocalSupabaseEnv, string>;

/** Parses `supabase status -o env` output: one `NAME="value"` per line. */
export function parseStatusEnv(output: string): Record<string, string> {
  return Object.fromEntries(
    output
      .split(/\r?\n/)
      .map((line) => /^([A-Z_]+)="(.*)"$/.exec(line.trim()))
      .filter((match): match is RegExpExecArray => match !== null)
      .map(([, name, value]) => [name, value]),
  );
}

function readStatus(): LocalSupabaseEnv {
  let output: string;
  try {
    output = execSync(`npx supabase status -o env --workdir "${REPO_ROOT}"`, {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    });
  } catch {
    throw new Error(`The local Supabase stack is not running. ${START_STACK_HINT}`);
  }
  const status = parseStatusEnv(output);
  const env = { apiUrl: status.API_URL, anonKey: status.ANON_KEY, serviceRoleKey: status.SERVICE_ROLE_KEY };
  if (!env.apiUrl || !env.anonKey || !env.serviceRoleKey) {
    throw new Error(`\`supabase status\` did not list API_URL, ANON_KEY and SERVICE_ROLE_KEY. ${START_STACK_HINT}`);
  }
  return env;
}

/** The local stack's settings, checked by the local-only guard; throws when they aren't local. */
export function readLocalSupabaseEnv(): LocalSupabaseEnv {
  const cached = {
    apiUrl: process.env[CACHED_ENV_NAMES.apiUrl],
    anonKey: process.env[CACHED_ENV_NAMES.anonKey],
    serviceRoleKey: process.env[CACHED_ENV_NAMES.serviceRoleKey],
  };
  const env =
    cached.apiUrl && cached.anonKey && cached.serviceRoleKey ? (cached as LocalSupabaseEnv) : readStatus();

  assertLocalSupabaseUrl(env.apiUrl);
  assertLocalSupabaseKey(env.anonKey);
  assertLocalSupabaseKey(env.serviceRoleKey);

  process.env[CACHED_ENV_NAMES.apiUrl] = env.apiUrl;
  process.env[CACHED_ENV_NAMES.anonKey] = env.anonKey;
  process.env[CACHED_ENV_NAMES.serviceRoleKey] = env.serviceRoleKey;
  return env;
}
