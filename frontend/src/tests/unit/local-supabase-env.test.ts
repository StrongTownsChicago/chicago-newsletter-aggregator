// @vitest-environment node
import { afterEach, describe, expect, it } from 'vitest';
import { parseStatusEnv, readLocalSupabaseEnv } from '../../../e2e/support/local-supabase-env';
import { NotLocalDatabaseError } from '../../../e2e/support/local-supabase-guard';

// The demo anon key every `supabase start` prints.
const LOCAL_ANON_KEY =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.' +
  'eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.' +
  'CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0';

const CACHED_NAMES = [
  'E2E_LOCAL_SUPABASE_API_URL',
  'E2E_LOCAL_SUPABASE_ANON_KEY',
  'E2E_LOCAL_SUPABASE_SERVICE_ROLE_KEY',
] as const;

describe('parseStatusEnv', () => {
  it('reads NAME="value" lines and skips anything else', () => {
    const output = [
      'Stopped services: [supabase_studio]',
      'API_URL="http://127.0.0.1:54321"',
      'ANON_KEY="a.b.c"\r',
      '',
    ].join('\n');

    expect(parseStatusEnv(output)).toEqual({ API_URL: 'http://127.0.0.1:54321', ANON_KEY: 'a.b.c' });
  });
});

describe('readLocalSupabaseEnv', () => {
  afterEach(() => {
    for (const name of CACHED_NAMES) delete process.env[name];
  });

  const cache = (apiUrl: string) => {
    process.env.E2E_LOCAL_SUPABASE_API_URL = apiUrl;
    process.env.E2E_LOCAL_SUPABASE_ANON_KEY = LOCAL_ANON_KEY;
    process.env.E2E_LOCAL_SUPABASE_SERVICE_ROLE_KEY = LOCAL_ANON_KEY;
  };

  it('returns cached local settings', () => {
    cache('http://127.0.0.1:54321');
    expect(readLocalSupabaseEnv()).toEqual({
      apiUrl: 'http://127.0.0.1:54321',
      anonKey: LOCAL_ANON_KEY,
      serviceRoleKey: LOCAL_ANON_KEY,
    });
  });

  it('guards cached settings too', () => {
    cache('https://abcdefghijklmnop.supabase.co');
    expect(() => readLocalSupabaseEnv()).toThrow(NotLocalDatabaseError);
  });
});
