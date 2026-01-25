import { vi } from 'vitest';
import type { APIContext } from 'astro';

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

export const createMockRequest = (formData?: Record<string, string | string[]>, method = 'POST') => {
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
    headers: new Headers(),
    url: 'http://localhost:4321',
  } as unknown as Request;
};

export const mockRedirect = vi.fn((url: string, status = 302) => {
  return new Response(null, {
    status,
    headers: { Location: url },
  });
});

export const createMockContext = (options: {
  formData?: Record<string, string | string[]>;
  method?: string;
  locals?: Record<string, unknown>;
} = {}) => {
  return {
    request: createMockRequest(options.formData, options.method),
    cookies: createMockCookies(),
    redirect: mockRedirect,
    locals: options.locals || {},
    url: new URL('http://localhost:4321'),
    params: {},
    site: undefined,
    generator: 'Astro',
  } as unknown as APIContext;
};
