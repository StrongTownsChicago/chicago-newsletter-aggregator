import { vi } from 'vitest';
import type { APIContext } from 'astro';
import type { SupabaseClient } from '@supabase/supabase-js';

export const createMockCookies = () => {
  const store = new Map<string, unknown>();
  return {
    get: vi.fn((key: string) => store.get(key)),
    set: vi.fn((key: string, value: string) => store.set(key, { value })),
    delete: vi.fn((key: string) => store.delete(key)),
    has: vi.fn((key: string) => store.has(key)),
    getAll: vi.fn(() => Array.from(store.values())),
  };
};

export const createMockRequest = (options: {
  formData?: Record<string, string | string[]>;
  json?: unknown;
  method?: string;
} = {}) => {
  const { formData, json, method = 'POST' } = options;
  return {
    method,
    formData: vi.fn(async () => ({
      get: (key: string) => {
        const val = formData?.[key];
        return Array.isArray(val) ? val[0] : (val || null);
      },
      getAll: (key: string) => {
        const val = formData?.[key];
        return Array.isArray(val) ? val : (val ? [val] : []);
      },
    })),
    json: vi.fn(async () => json || {}),
    headers: new Headers(),
    url: 'http://localhost:4321',
  } as unknown as Request;
};

export const createMockSupabase = () => {
  const mock = {
    from: vi.fn().mockReturnThis(),
    select: vi.fn().mockReturnThis(),
    update: vi.fn().mockReturnThis(),
    delete: vi.fn().mockReturnThis(),
    eq: vi.fn().mockReturnThis(),
    single: vi.fn().mockReturnThis(),
    insert: vi.fn().mockReturnThis(),
    in_: vi.fn().mockReturnThis(),
    auth: {
      getSession: vi.fn(),
      setSession: vi.fn(),
      signInWithPassword: vi.fn(),
      signUp: vi.fn(),
      signOut: vi.fn(),
    },
  };
  return mock as unknown as SupabaseClient;
};

export const mockRedirect = vi.fn((url: string, status = 302) => {
  return new Response(null, {
    status,
    headers: { Location: url },
  });
});

export const createMockContext = (options: {
  formData?: Record<string, string | string[]>;
  json?: unknown;
  method?: string;
  locals?: Record<string, unknown>;
} = {}) => {
  return {
    request: createMockRequest({ formData: options.formData, json: options.json, method: options.method }),
    cookies: createMockCookies(),
    redirect: mockRedirect,
    locals: options.locals || {},
    url: new URL('http://localhost:4321'),
    params: {},
    site: undefined,
    generator: 'Astro',
  } as unknown as APIContext;
};
