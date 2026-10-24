import { describe, expect, it } from 'vitest';
import {
  assertLocalSupabaseKey,
  assertLocalSupabaseUrl,
  NotLocalDatabaseError,
} from '../../../e2e/support/local-supabase-guard';

// The demo anon key every `supabase start` prints.
const LOCAL_ANON_KEY =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.' +
  'eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.' +
  'CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0';

function unsignedJwt(claims: Record<string, unknown>): string {
  const encode = (part: object) => Buffer.from(JSON.stringify(part)).toString('base64url');
  return `${encode({ alg: 'HS256', typ: 'JWT' })}.${encode(claims)}.signature`;
}

describe('assertLocalSupabaseUrl', () => {
  it.each(['http://127.0.0.1:54321', 'http://localhost:54321/rest/v1', 'http://[::1]:54321'])('accepts %s', (url) => {
    expect(() => assertLocalSupabaseUrl(url)).not.toThrow();
  });

  it.each([
    'https://abcdefghijklmnopqrst.supabase.co',
    'postgresql://postgres.abcdefghijklmnopqrst:pw@aws-0-us-east-1.pooler.supabase.com:5432/postgres',
    'http://127.0.0.1.example.com:54321',
    'http://localhost.supabase.co',
    '',
    'not a url',
  ])('rejects %s', (url) => {
    expect(() => assertLocalSupabaseUrl(url)).toThrow(NotLocalDatabaseError);
  });
});

describe('assertLocalSupabaseKey', () => {
  it('accepts the local demo key', () => {
    expect(() => assertLocalSupabaseKey(LOCAL_ANON_KEY)).not.toThrow();
  });

  it('rejects a key naming a hosted project', () => {
    const hosted = unsignedJwt({ iss: 'supabase', ref: 'abcdefghijklmnopqrst', role: 'anon' });
    expect(() => assertLocalSupabaseKey(hosted)).toThrow(/abcdefghijklmnopqrst/);
  });

  it.each([
    unsignedJwt({ iss: 'supabase-demo', ref: 'abc' }),
    unsignedJwt({ iss: 'supabase', role: 'anon' }),
    unsignedJwt({ role: 'anon' }),
    'sb_publishable_abcdefghijklmnopqrstuv',
    'placeholder-anon-key',
    'a.!!!.c',
    '',
  ])('rejects %s', (key) => {
    expect(() => assertLocalSupabaseKey(key)).toThrow(NotLocalDatabaseError);
  });
});
