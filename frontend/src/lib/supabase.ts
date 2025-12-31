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
  source_name: string | null;
  source_type: string | null;
  source_metadata: any;
  plain_text: string;
  summary: string | null;
  topics: string[] | null;
  entities: any;
}

export interface Source {
  id: number;
  source_type: string;
  name: string;
  email_address: string | null;
  website: string | null;
  metadata: any;
}
