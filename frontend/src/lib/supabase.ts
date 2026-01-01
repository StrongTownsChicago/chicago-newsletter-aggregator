import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.PUBLIC_SUPABASE_ANON_KEY;

export const supabase = createClient(supabaseUrl, supabaseAnonKey);

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
