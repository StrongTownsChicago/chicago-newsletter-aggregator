import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock Supabase
const mockSupabase = {
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

import { onRequest } from '../middleware';
import { createMockContext } from './helpers';

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
    vi.mocked(context.cookies.get).mockImplementation((key) => {
        if (key === 'sb-access-token') return { value: 'access-123' } as any;
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

  it('sets user and session in locals if session exists', async () => {
    const mockSession = { user: { id: 'user-123' }, access_token: 'abc' };
    mockSupabase.auth.getSession.mockResolvedValue({ data: { session: mockSession }, error: null });

    const context = createMockContext();
    const next = vi.fn(() => Promise.resolve(new Response()));

    await onRequest(context, next);

    expect(context.locals.session).toBe(mockSession);
    expect(context.locals.user).toBe(mockSession.user);
  });
});
