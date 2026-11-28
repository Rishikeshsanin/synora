-- Local experimental provider only; apply to disposable development databases, never live.
begin;
alter table synora.jobs add column experimental_config jsonb;
alter table synora.jobs add column upstream_job_id text check (length(upstream_job_id) between 1 and 128);
alter table synora.jobs add column reconciliation_required boolean not null default false;
alter table synora.jobs add constraint local_ace_experimental_config check (
  (experimental_config is null and not reconciliation_required and upstream_job_id is null)
  or (provider='ace-step' and not simulated and experimental_config is not null)
);
create index jobs_local_ace_reconcile on synora.jobs(reconciliation_required) where provider='ace-step' and reconciliation_required;
commit;
