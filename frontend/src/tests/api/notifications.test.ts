import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock lib/supabase
vi.mock('../../lib/supabase', () => ({
  notificationsEnabled: vi.fn(() => true),
}));

import { POST as createRulePOST } from '../../pages/api/notifications/create-rule';
import { POST as deleteRulePOST } from '../../pages/api/notifications/delete-rule';
import { POST as updatePreferencesPOST } from '../../pages/api/notifications/update-preferences';
import { POST as updateRulePOST } from '../../pages/api/notifications/update-rule';
import { createMockContext } from '../helpers';
import { notificationsEnabled } from '../../lib/supabase';

describe('Notifications API Routes', () => {
  let mockSupabase: any;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(notificationsEnabled).mockReturnValue(true);

    // Deeply mocked supabase client
    mockSupabase = {
      from: vi.fn().mockReturnThis(),
      select: vi.fn().mockReturnThis(),
      eq: vi.fn().mockReturnThis(),
      insert: vi.fn().mockReturnThis(),
      update: vi.fn().mockReturnThis(),
      delete: vi.fn().mockReturnThis(),
    };
  });

  describe('POST /api/notifications/create-rule', () => {
    it('redirects to /login if not authenticated', async () => {
      const context = createMockContext({ locals: { user: null } });
      const response = await createRulePOST(context);
      expect(response.status).toBe(302);
      expect(response.headers.get('Location')).toBe('/login');
    });

    it('creates a search rule successfully', async () => {
      // Mock the final call in the chain to resolve with data
      mockSupabase.eq.mockResolvedValueOnce({ count: 2, error: null });
      mockSupabase.insert.mockResolvedValueOnce({ error: null });

      const context = createMockContext({
        locals: { user: { id: 'user-123' }, supabase: mockSupabase },
        formData: {
          name: 'My Search Rule',
          rule_type: 'search',
          search_term: 'Chicago Police',
          is_active: 'on'
        }
      });

      const response = await createRulePOST(context);

      expect(response.status).toBe(302);
      expect(response.headers.get('Location')).toContain('message=Rule created successfully');
      expect(mockSupabase.from).toHaveBeenCalledWith('notification_rules');
      expect(mockSupabase.insert).toHaveBeenCalledWith(expect.objectContaining({
        user_id: 'user-123',
        name: 'My Search Rule',
        search_term: 'Chicago Police',
        topics: [],
        is_active: true
      }));
    });

    it('creates a topic rule successfully', async () => {
      // Mock the final call in the chain to resolve with data
      mockSupabase.eq.mockResolvedValueOnce({ count: 2, error: null });
      mockSupabase.insert.mockResolvedValueOnce({ error: null });

      const context = createMockContext({
        locals: { user: { id: 'user-123' }, supabase: mockSupabase },
        formData: {
          name: 'My Topic Rule',
          rule_type: 'topic',
          topics: ['Politics', 'Education'],
          is_active: 'on'
        }
      });

      const response = await createRulePOST(context);

      expect(response.status).toBe(302);
      expect(response.headers.get('Location')).toContain('message=Rule created successfully');
      expect(mockSupabase.insert).toHaveBeenCalledWith(expect.objectContaining({
        topics: ['Politics', 'Education'],
        search_term: null
      }));
    });

    it('returns error if rule limit reached', async () => {
      mockSupabase.eq.mockResolvedValueOnce({ count: 5, error: null });

      const context = createMockContext({
        locals: { user: { id: 'user-123' }, supabase: mockSupabase },
        formData: {
          name: 'Too Many Rules',
          rule_type: 'topic',
          topics: ['Politics']
        }
      });

      const response = await createRulePOST(context);
      expect(response.status).toBe(302);
      expect(response.headers.get('Location')).toContain('error=Maximum 5 rules allowed');
    });

    it('returns 404 if notifications are disabled', async () => {
      vi.mocked(notificationsEnabled).mockReturnValue(false);
      const context = createMockContext({ locals: { user: { id: '1' } } });
      const response = await createRulePOST(context);
      expect(response.status).toBe(404);
    });

    it('redirects with error if name is missing', async () => {
      const context = createMockContext({
        locals: { user: { id: 'user-123' } },
        formData: { rule_type: 'search', search_term: 'test' }
      });
      const response = await createRulePOST(context);
      expect(response.headers.get('Location')).toContain('error=Rule name is required');
    });

    it('redirects with error if search term is missing in search mode', async () => {
      const context = createMockContext({
        locals: { user: { id: 'user-123' } },
        formData: { name: 'My Rule', rule_type: 'search' }
      });
      const response = await createRulePOST(context);
      expect(response.headers.get('Location')).toContain('error=Search phrase is required');
    });

    it('redirects with error if topics are missing in topic mode', async () => {
      const context = createMockContext({
        locals: { user: { id: 'user-123' } },
        formData: { name: 'My Rule', rule_type: 'topic', topics: [] }
      });
      const response = await createRulePOST(context);
      expect(response.headers.get('Location')).toContain('error=At least one topic is required');
    });
  });

  describe('POST /api/notifications/delete-rule', () => {
    it('deletes a rule successfully', async () => {
      // First eq returns the builder, second eq resolves
      mockSupabase.eq.mockReturnValueOnce(mockSupabase);
      mockSupabase.eq.mockResolvedValueOnce({ error: null });

      const context = createMockContext({
        locals: { user: { id: 'user-123' }, supabase: mockSupabase },
        formData: { rule_id: 'rule-456' }
      });

      const response = await deleteRulePOST(context);

      expect(response.status).toBe(302);
      expect(response.headers.get('Location')).toContain('message=Rule deleted successfully');
      expect(mockSupabase.from).toHaveBeenCalledWith('notification_rules');
      expect(mockSupabase.delete).toHaveBeenCalled();
      expect(mockSupabase.eq).toHaveBeenCalledWith('id', 'rule-456');
    });
  });

  describe('POST /api/notifications/update-preferences', () => {
    it('updates preferences successfully', async () => {
      mockSupabase.eq.mockResolvedValueOnce({ error: null });

      const context = createMockContext({
        locals: { user: { id: 'user-123' }, supabase: mockSupabase },
        formData: { enabled: 'on' }
      });

      const response = await updatePreferencesPOST(context);

      expect(response.status).toBe(302);
      expect(response.headers.get('Location')).toContain('message=Preferences updated successfully');
      expect(mockSupabase.from).toHaveBeenCalledWith('user_profiles');
      expect(mockSupabase.update).toHaveBeenCalledWith(expect.objectContaining({
        notification_preferences: expect.objectContaining({ enabled: true })
      }));
    });
  });

  describe('POST /api/notifications/update-rule', () => {
    it('updates a rule successfully', async () => {
      // First eq returns the builder, second eq resolves
      mockSupabase.eq.mockReturnValueOnce(mockSupabase);
      mockSupabase.eq.mockResolvedValueOnce({ error: null });

      const context = createMockContext({
        locals: { user: { id: 'user-123' }, supabase: mockSupabase },
        formData: {
          rule_id: 'rule-456',
          name: 'Updated Rule Name',
          rule_type: 'topic',
          topics: ['Crime'],
          is_active: 'on'
        }
      });

      const response = await updateRulePOST(context);

      expect(response.status).toBe(302);
      expect(response.headers.get('Location')).toContain('message=Rule updated successfully');
      expect(mockSupabase.from).toHaveBeenCalledWith('notification_rules');
      expect(mockSupabase.update).toHaveBeenCalledWith(expect.objectContaining({
        name: 'Updated Rule Name',
        topics: ['Crime']
      }));
      expect(mockSupabase.eq).toHaveBeenCalledWith('id', 'rule-456');
    });
  });
});
