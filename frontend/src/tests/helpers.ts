import { vi } from 'vitest';
import type { APIRoute } from 'astro';

export const createMockCookies = () => {
  const store = new Map<string, any>();
  return {
    get: vi.fn((key) => store.get(key)),
    set: vi.fn((key, value, options) => store.set(key, { value, ...options })),
    delete: vi.fn((key) => store.delete(key)),
    has: vi.fn((key) => store.has(key)),
    getAll: vi.fn(() => Array.from(store.values())),
    store, // Expose store for assertions if needed
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

export const mockRedirect = vi.fn((url, status = 302) => {
  return new Response(null, {
    status,
    headers: { Location: url },
  });
});

export const createMockContext = (options: {
  formData?: Record<string, string>;
  method?: string;
  locals?: any;
} = {}) => {
  return {
    request: createMockRequest(options.formData, options.method),
    cookies: createMockCookies(),
    redirect: mockRedirect,
    locals: options.locals || {},
  } as any;
};
