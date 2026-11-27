-- Synora-only schema. Do not apply to a shared/live project without approval.
begin;
create schema synora;
revoke all on schema synora from public, anon, authenticated;
create table synora.projects (
 id uuid primary key default gen_random_uuid(), user_id uuid not null,
 name text not null check(length(name) between 1 and 120),
 created_at timestamptz not null default now(), unique(id,user_id)
);
create table synora.jobs (
 id uuid primary key default gen_random_uuid(), user_id uuid not null,
 project_id uuid, kind text not null default 'music' check(kind in ('music','advertisement')),
 spec jsonb not null, idempotency_key text not null check(length(idempotency_key) between 1 and 128),
 request_hash text not null, status text not null default 'queued' check(status in ('queued','running','succeeded','failed','cancelled')),
 progress integer not null default 0 check(progress between 0 and 100),
 provider text, simulated boolean not null, error jsonb, asset_id uuid,
 attempts integer not null default 0 check(attempts between 0 and 3),
 lease_token uuid, lease_until timestamptz, available_at timestamptz not null default now(),
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 unique(user_id,idempotency_key), unique(id,user_id),
 foreign key(project_id,user_id) references synora.projects(id,user_id),
 check ((status='running') = (lease_token is not null and lease_until is not null)),
 check ((status='succeeded') = (asset_id is not null)),
 check (status <> 'succeeded' or progress=100)
);
create index jobs_claim on synora.jobs(available_at,created_at) where status='queued';
create index jobs_recover on synora.jobs(lease_until) where status='running';
create index jobs_owner_created on synora.jobs(user_id,created_at desc);
create table synora.assets (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, job_id uuid not null unique,
 kind text not null check(kind in ('audio','video','image')), mime_type text not null,
 duration_seconds numeric check(duration_seconds>0), storage_key text not null unique,
 simulated boolean not null, provenance jsonb not null default '{}',
 created_at timestamptz not null default now(), unique(id,user_id),
 foreign key(job_id,user_id) references synora.jobs(id,user_id)
);
alter table synora.jobs add foreign key(asset_id,user_id) references synora.assets(id,user_id);
-- Reservation record is deliberately zero-value; no balance or payment integration.
create table synora.credit_reservations (
 job_id uuid primary key references synora.jobs(id), units integer not null default 0 check(units=0),
 status text not null default 'reserved' check(status in ('reserved','settled','released')),
 updated_at timestamptz not null default now()
);
alter table synora.projects enable row level security;
alter table synora.jobs enable row level security;
alter table synora.assets enable row level security;
alter table synora.credit_reservations enable row level security;
-- Defense in depth. No direct client grants; API is the only write path.
create policy projects_owner on synora.projects for select to authenticated using ((select auth.uid())=user_id);
create policy jobs_owner on synora.jobs for select to authenticated using ((select auth.uid())=user_id);
create policy assets_owner on synora.assets for select to authenticated using ((select auth.uid())=user_id);
revoke all on all tables in schema synora from public, anon, authenticated;
-- Supabase service_role is server only. Prefer a separately provisioned restricted login
-- with equivalent schema privileges for direct PostgreSQL connections.
grant usage on schema synora to service_role;
grant select,insert,update,delete on all tables in schema synora to service_role;
commit;
