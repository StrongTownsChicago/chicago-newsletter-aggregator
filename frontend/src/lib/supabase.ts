import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.PUBLIC_SUPABASE_ANON_KEY;

// Create Supabase client with auth enabled
export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
  },
});

export interface Newsletter {
  id: string;
  created_at: string;
  received_date: string;
  subject: string;
  from_email: string;
  source_id: number | null;
  plain_text: string;
  raw_html: string | null;
  summary: string | null;
  topics: string[] | null;
  relevance_score: number | null;
  entities: any;
  sources?: Source;
}

export interface Source {
  id: number;
  source_type: string;
  name: string;
  email_address: string | null;
  website: string | null;
  signup_url: string | null;
  ward_number: string | null;
  phone: string | null;
}

export interface UserProfile {
  id: string;
  email: string;
  created_at: string;
  updated_at: string;
  notification_preferences: {
    enabled: boolean;
    delivery_frequency: string;
  };
}

export interface NotificationRule {
  id: string;
  user_id: string;
  name: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  topics: string[];
  search_term?: string;
  min_relevance_score?: number;
  source_ids?: number[];
  ward_numbers?: string[]; // TEXT[] to match sources.ward_number TEXT type
}
