# Master integration checkpoint

This branch combines exact specialist PR snapshots for local/CI integration only, not release or production. Main stays unchanged. Original draft PRs remain open.
- PR #7: c95daa9f992ca158652fb940a2ae29b325c8da55
- PR #8: de536a3e9ad46c79a3ed86b2b469581a6ab44277
- PR #9: dc439e8e9c86f9a6057a050981b76be8394e8e07
- PR #10: 86340e5bae7f252669c98760e293a2058fc9ca3d
- PR #11: 7f47b6a9991e1756e7760437607ac32acd3782c1
- PR #12: d44b48dfffc655c5624d5cc571145a151b0ad2e7

Known blockers from source inspection:
- Web package.json lacks lint script and npm lockfile required by CI. Frontend owner must supply lockfile, lint, typecheck, build and browser evidence.
- Python CI requires hashed requirements-dev.lock in each component; none are present. DevOps to align Python 3.12, actual test commands and locks, include disposable Postgres/RLS and browser suite. Do not remove gates.
- Infrastructure Dockerfile expects requirements.lock and app.main:app, while API uses synora.api:app. DevOps/backend to agree one build context and entry point.
- Backend worker uses a byte-returning FixtureProvider with callback; engines/music uses MusicOutput path and GenerationContext. Backend/music owners to implement one adapter, one canonical fixture for server generation, capability validation and cancellation/lease handling. Production real generation remains disabled.
- QA to verify integrated code at exact SHA; frontend local demo remains clearly labeled. Offline media stays isolated until M1 is verified.

No paid API calls, live migrations, deployment or production release. Integration CI is expected to reveal missing prerequisites; failures are actionable, not to be suppressed.
