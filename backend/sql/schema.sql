create table public.sources (
  id serial not null,
  source_type text not null,
  name text not null,
  email_address text null,
  website text null,
  signup_url text null,
  ward_number text null,
  phone text null,
  newsletter_archive_url text null,
  constraint sources_pkey primary key (id),
  constraint sources_source_type_name_key unique (source_type, name)
) TABLESPACE pg_default;

create index IF not exists idx_sources_ward_number on public.sources using btree (ward_number) TABLESPACE pg_default;

create index IF not exists idx_sources_phone on public.sources using btree (phone) TABLESPACE pg_default;

---

create table public.newsletters (
  id uuid not null default gen_random_uuid (),
  created_at timestamp with time zone null default now(),
  email_uid text null,
  received_date timestamp with time zone not null,
  subject text not null,
  from_email text null,
  to_email text null,
  raw_html text null,
  plain_text text null,
  summary text null,
  topics text[] null,
  entities jsonb null,
  source_id integer not null,
  search_vector tsvector GENERATED ALWAYS as (
    to_tsvector(
      'english'::regconfig,
      (
        (COALESCE(subject, ''::text) || ' '::text) || COALESCE(plain_text, ''::text)
      )
    )
  ) STORED null,
  relevance_score integer null,
  constraint newsletters_pkey primary key (id),
  constraint newsletters_email_uid_key unique (email_uid),
  constraint newsletters_source_id_fkey foreign KEY (source_id) references sources (id) on delete set null,
  constraint newsletters_relevance_score_check check (
    (
      (relevance_score >= 0)
      and (relevance_score <= 10)
    )
  )
) TABLESPACE pg_default;

create index IF not exists newsletters_received_date_idx on public.newsletters using btree (received_date desc) TABLESPACE pg_default;

create index IF not exists newsletters_topics_idx on public.newsletters using gin (topics) TABLESPACE pg_default;

create index IF not exists idx_newsletters_source_id on public.newsletters using btree (source_id) TABLESPACE pg_default;

create index IF not exists idx_newsletters_search on public.newsletters using gin (search_vector) TABLESPACE pg_default;

create index IF not exists idx_newsletters_relevance on public.newsletters using btree (relevance_score) TABLESPACE pg_default;

---

create table public.email_source_mappings (
  id serial not null,
  email_pattern text not null,
  source_id integer not null,
  notes text null,
  created_at timestamp with time zone null default now(),
  constraint email_source_mappings_pkey primary key (id),
  constraint email_source_mappings_source_id_fkey foreign KEY (source_id) references sources (id) on delete CASCADE
) TABLESPACE pg_default;

create index IF not exists idx_email_source_mappings_pattern on public.email_source_mappings using btree (email_pattern) TABLESPACE pg_default;

---
-- NOTIFICATION SYSTEM TABLES
---

create table public.user_profiles (
  id uuid not null,
  email text not null,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  notification_preferences jsonb not null default '{"enabled": true, "delivery_frequency": "daily"}'::jsonb,
  constraint user_profiles_pkey primary key (id),
  constraint user_profiles_id_fkey foreign key (id) references auth.users (id) on delete cascade
) TABLESPACE pg_default;

alter table public.user_profiles enable row level security;

create policy "Users can view own profile" on public.user_profiles
  for select using (auth.uid() = id);

create policy "Users can update own profile" on public.user_profiles
  for update using (auth.uid() = id);

create index if not exists idx_user_profiles_email on public.user_profiles using btree (email) TABLESPACE pg_default;

---

create table public.notification_rules (
  id uuid not null default gen_random_uuid(),
  user_id uuid not null,
  name text not null,
  is_active boolean not null default true,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  topics text[] not null default '{}',
  search_term text null,
  min_relevance_score integer null,
  source_ids integer[] null,
  ward_numbers text[] null,
  constraint notification_rules_pkey primary key (id),
  constraint notification_rules_user_id_fkey foreign key (user_id) references auth.users (id) on delete cascade
) TABLESPACE pg_default;

alter table public.notification_rules enable row level security;

create policy "Users can view own rules" on public.notification_rules
  for select using (auth.uid() = user_id);

create policy "Users can create own rules" on public.notification_rules
  for insert with check (auth.uid() = user_id);

create policy "Users can update own rules" on public.notification_rules
  for update using (auth.uid() = user_id);

create policy "Users can delete own rules" on public.notification_rules
  for delete using (auth.uid() = user_id);

create index if not exists idx_notification_rules_user_id on public.notification_rules using btree (user_id) TABLESPACE pg_default;

create index if not exists idx_notification_rules_active on public.notification_rules using btree (user_id, is_active) TABLESPACE pg_default;

---

create table public.notification_queue (
  id uuid not null default gen_random_uuid(),
  user_id uuid not null,
  newsletter_id uuid not null,
  rule_id uuid not null,
  status text not null default 'pending',
  digest_batch_id text null,
  created_at timestamp with time zone not null default now(),
  sent_at timestamp with time zone null,
  error_message text null,
  constraint notification_queue_pkey primary key (id),
  constraint notification_queue_user_id_fkey foreign key (user_id) references auth.users (id) on delete cascade,
  constraint notification_queue_newsletter_id_fkey foreign key (newsletter_id) references newsletters (id) on delete cascade,
  constraint notification_queue_rule_id_fkey foreign key (rule_id) references notification_rules (id) on delete cascade,
  constraint notification_queue_status_check check (status in ('pending', 'sent', 'failed')),
  constraint unique_notification unique (user_id, newsletter_id, rule_id)
) TABLESPACE pg_default;

alter table public.notification_queue enable row level security;

create policy "Users can view own queued notifications" on public.notification_queue
  for select using (auth.uid() = user_id);

create index if not exists idx_notification_queue_status on public.notification_queue using btree (status, created_at) TABLESPACE pg_default;

create index if not exists idx_notification_queue_user on public.notification_queue using btree (user_id, status) TABLESPACE pg_default;

create index if not exists idx_notification_queue_digest on public.notification_queue using btree (digest_batch_id, status) TABLESPACE pg_default;

---

create table public.notification_history (
  id uuid not null default gen_random_uuid(),
  user_id uuid not null,
  newsletter_ids uuid[] not null,
  rule_ids uuid[] not null,
  digest_batch_id text null,
  delivery_type text not null,
  sent_at timestamp with time zone not null default now(),
  success boolean not null,
  error_message text null,
  resend_email_id text null,
  constraint notification_history_pkey primary key (id),
  constraint notification_history_user_id_fkey foreign key (user_id) references auth.users (id) on delete cascade,
  constraint notification_history_delivery_type_check check (delivery_type in ('immediate', 'daily_digest', 'weekly_digest'))
) TABLESPACE pg_default;

alter table public.notification_history enable row level security;

create policy "Users can view own notification history" on public.notification_history
  for select using (auth.uid() = user_id);

create index if not exists idx_notification_history_user on public.notification_history using btree (user_id, sent_at desc) TABLESPACE pg_default;

create index if not exists idx_notification_history_batch on public.notification_history using btree (digest_batch_id) TABLESPACE pg_default;

create index if not exists idx_notification_history_success on public.notification_history using btree (success, sent_at desc) TABLESPACE pg_default;

---
-- TRIGGERS AND FUNCTIONS
---

-- Auto-create user profile on signup
create or replace function public.create_user_profile()
returns trigger as $$
begin
  insert into public.user_profiles (id, email)
  values (new.id, new.email);
  return new;
end;
$$ language plpgsql security definer;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row
  execute function public.create_user_profile();

-- Auto-update updated_at timestamp
create or replace function public.update_updated_at_column()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists update_user_profiles_updated_at on public.user_profiles;
create trigger update_user_profiles_updated_at
  before update on public.user_profiles
  for each row
  execute function public.update_updated_at_column();

drop trigger if exists update_notification_rules_updated_at on public.notification_rules;
create trigger update_notification_rules_updated_at
  before update on public.notification_rules
  for each row
  execute function public.update_updated_at_column();

-- Helper function: count user rules
create or replace function public.count_user_rules(user_uuid uuid)
returns integer as $$
  select count(*)::integer
  from public.notification_rules
  where user_id = user_uuid;
$$ language sql stable;

grant execute on function public.count_user_rules to authenticated;