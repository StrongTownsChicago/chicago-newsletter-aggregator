import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

interface MockSupabase {
  auth: {
    setSession: ReturnType<typeof vi.fn>;
    getSession: ReturnType<typeof vi.fn>;
  };
}

// Mock Supabase
const mockSupabase: MockSupabase = {
  auth: {
    setSession: vi.fn(),
    getSession: vi.fn(),
  },
};

vi.mock('@supabase/supabase-js', () => ({
  createClient: vi.fn(() => mockSupabase),
}));

// Mock astro:middleware - this is a virtual module in Astro
vi.mock('astro:middleware', () => ({
  defineMiddleware: vi.fn((cb) => cb),
}));

import { createClient } from '@supabase/supabase-js';
import { onRequest } from '../middleware';
import { PAGE_CACHE_HEADER } from '../lib/server/page-cache';
import { createMockContext } from './helpers';
import type { APIContext } from 'astro';

describe('Middleware', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSupabase.auth.getSession.mockResolvedValue({ data: { session: null }, error: null });
  });

  it('injects supabase client into locals', async () => {
    const context = createMockContext();
    const next = vi.fn(() => Promise.resolve(new Response()));

    await onRequest(context, next);

    expect(context.locals.supabase).toBeDefined();
    expect(next).toHaveBeenCalled();
  });

  it('restores session from cookies if present', async () => {
    const context = createMockContext();
    // Simulate cookies being present
    vi.mocked(context.cookies.get).mockImplementation((key: string) => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        if (key === 'sb-access-token') return { value: 'access-123' } as any;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        if (key === 'sb-refresh-token') return { value: 'refresh-123' } as any;
        return undefined;
    });
    
    const next = vi.fn(() => Promise.resolve(new Response()));

    await onRequest(context, next);

    expect(mockSupabase.auth.setSession).toHaveBeenCalledWith({
      access_token: 'access-123',
      refresh_token: 'refresh-123',
    });
  });

  it('builds a per-request client that neither persists nor refreshes the session', async () => {
    await onRequest(createMockContext(), vi.fn(() => Promise.resolve(new Response())));

    expect(vi.mocked(createClient).mock.calls[0][2]).toEqual({
      auth: { persistSession: false, autoRefreshToken: false },
    });
  });

  it.each(['sb-access-token', 'sb-refresh-token'])(
    'does not restore a session from %s alone',
    async (cookieName) => {
      const context = createMockContext();
      vi.mocked(context.cookies.get).mockImplementation((key: string) =>
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        key === cookieName ? ({ value: 'token-123' } as any) : undefined,
      );

      await onRequest(context, vi.fn(() => Promise.resolve(new Response())));

      expect(mockSupabase.auth.setSession).not.toHaveBeenCalled();
    },
  );

  it('does not read cookies while prerendering a page at build time', async () => {
    const context = { ...createMockContext(), isPrerendered: true } as APIContext;
    const next = vi.fn(() => Promise.resolve(new Response()));

    await onRequest(context, next);

    expect(context.cookies.get).not.toHaveBeenCalled();
    expect(mockSupabase.auth.setSession).not.toHaveBeenCalled();
    expect(context.locals.user).toBeNull();
  });

  it('sets user and session in locals if session exists', async () => {
    const mockSession = { user: { id: 'user-123' }, access_token: 'abc' };
    mockSupabase.auth.getSession.mockResolvedValue({ data: { session: mockSession }, error: null });

    const context = createMockContext();
    const next = vi.fn(() => Promise.resolve(new Response()));

    await onRequest(context, next);

    expect(context.locals.session).toBe(mockSession);
    expect(context.locals.user).toBe(mockSession.user);
  });

  describe('X-Robots-Tag', () => {
    const productionSite = new URL('https://chicago-newsletter-aggregator.open-advocacy.com');

    const runOnHost = async (requestUrl: string) => {
      const context = {
        ...createMockContext(),
        url: new URL(requestUrl),
        site: productionSite,
      } as unknown as APIContext;
      const next = vi.fn(() => Promise.resolve(new Response()));
      return onRequest(context, next) as Promise<Response>;
    };

    it('does not add noindex on the production host', async () => {
      const response = await runOnHost('https://chicago-newsletter-aggregator.open-advocacy.com/search');

      expect(response.headers.get('X-Robots-Tag')).toBeNull();
    });

    it('adds noindex on Cloudflare Pages preview hosts', async () => {
      const response = await runOnHost('https://abc123.chicago-newsletter-aggregator.pages.dev/');

      expect(response.headers.get('X-Robots-Tag')).toBe('noindex');
    });
  });
  describe('page cache', () => {
    const productionOrigin = 'https://chicago-newsletter-aggregator.open-advocacy.com';
    const previewOrigin = 'https://abc123.chicago-newsletter-aggregator.pages.dev';

    /** In-memory stand-in for the Workers Cache API. */
    const createMemoryCache = () => {
      const entries = new Map<string, Response>();
      return {
        match: vi.fn(async (request: Request) => entries.get(request.url)?.clone()),
        put: vi.fn(async (request: Request, response: Response) => {
          entries.set(request.url, response);
        }),
      };
    };

    let cache: ReturnType<typeof createMemoryCache>;

    beforeEach(() => {
      cache = createMemoryCache();
      vi.stubGlobal('caches', { default: cache });
    });

    afterEach(() => {
      vi.unstubAllGlobals();
    });

    const pageContext = (path: string, origin = productionOrigin, locals: Record<string, unknown> = {}) =>
      ({
        ...createMockContext({ method: 'GET', locals }),
        url: new URL(path, origin),
        site: new URL(productionOrigin),
        isPrerendered: false,
      }) as unknown as APIContext;

    const renderPage = (body = '<p>page</p>') =>
      vi.fn(() => Promise.resolve(new Response(body, { headers: { 'Content-Type': 'text/html' } })));

    it('serves a repeat anonymous view from the cache without session work', async () => {
      const firstNext = renderPage('<p>ward 1</p>');
      const first = (await onRequest(pageContext('/ward/1'), firstNext)) as Response;

      expect(first.headers.get(PAGE_CACHE_HEADER)).toBe('miss');
      expect(first.headers.get('Cache-Control')).toBe('no-cache');
      expect(cache.put).toHaveBeenCalledTimes(1);

      vi.clearAllMocks();
      const secondNext = renderPage();
      const second = (await onRequest(pageContext('/ward/1'), secondNext)) as Response;

      expect(second.headers.get(PAGE_CACHE_HEADER)).toBe('hit');
      expect(second.headers.get('Cache-Control')).toBe('no-cache');
      expect(await second.text()).toBe('<p>ward 1</p>');
      expect(secondNext).not.toHaveBeenCalled();
      expect(createClient).not.toHaveBeenCalled();
      expect(mockSupabase.auth.getSession).not.toHaveBeenCalled();
    });

    it('renders signed-in views without the cache', async () => {
      const context = pageContext('/');
      vi.mocked(context.cookies.get).mockImplementation((key: string) =>
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        key === 'sb-access-token' ? ({ value: 'access-123' } as any) : undefined,
      );
      const next = renderPage();

      const response = (await onRequest(context, next)) as Response;

      expect(response.headers.get(PAGE_CACHE_HEADER)).toBe('bypass');
      expect(next).toHaveBeenCalled();
      expect(cache.match).not.toHaveBeenCalled();
      expect(cache.put).not.toHaveBeenCalled();
    });

    it('does not store a page that set cookies while rendering', async () => {
      const context = pageContext('/');
      const next = vi.fn(() => {
        context.cookies.set('flash', 'saved');
        return Promise.resolve(new Response('<p/>'));
      });

      await onRequest(context, next);

      expect(cache.put).not.toHaveBeenCalled();
    });

    it('stores through the Cloudflare waitUntil when available', async () => {
      const waitUntil = vi.fn();
      const context = pageContext('/newsletter/5', productionOrigin, { runtime: { ctx: { waitUntil } } });

      await onRequest(context, renderPage());

      expect(waitUntil).toHaveBeenCalledWith(expect.any(Promise));
      await waitUntil.mock.calls[0][0];
      expect(cache.put).toHaveBeenCalledTimes(1);
    });

    it('leaves routes outside the allowlist alone', async () => {
      const response = (await onRequest(pageContext('/preferences'), renderPage())) as Response;

      expect(response.headers.get(PAGE_CACHE_HEADER)).toBeNull();
      expect(cache.match).not.toHaveBeenCalled();
    });

    it('adds noindex on preview hosts for misses and hits', async () => {
      const miss = (await onRequest(pageContext('/wards', previewOrigin), renderPage())) as Response;
      const hit = (await onRequest(pageContext('/wards', previewOrigin), renderPage())) as Response;

      expect(miss.headers.get(PAGE_CACHE_HEADER)).toBe('miss');
      expect(hit.headers.get(PAGE_CACHE_HEADER)).toBe('hit');
      expect(miss.headers.get('X-Robots-Tag')).toBe('noindex');
      expect(hit.headers.get('X-Robots-Tag')).toBe('noindex');
    });

    it('keeps preview copies separate from production', async () => {
      await onRequest(pageContext('/wards', previewOrigin), renderPage());
      const production = (await onRequest(pageContext('/wards'), renderPage())) as Response;

      expect(production.headers.get(PAGE_CACHE_HEADER)).toBe('miss');
      expect(production.headers.get('X-Robots-Tag')).toBeNull();
    });
  });
});
