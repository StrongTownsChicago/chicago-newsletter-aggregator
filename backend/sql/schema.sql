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