# Architecture (initial decisions)

M1: prompt -> validated music spec -> durable job -> provider -> private asset -> playback/export.
M2: uploaded rights-cleared assets + brand brief -> 3-5 concepts -> approval -> storyboard + music job + media render -> QC -> export. M2 must reuse M1 job/asset contracts. No unverified business claims or altered logos presented as authentic.

Frontend Next.js/React/TypeScript/Tailwind, WaveSurfer; backend FastAPI/Python 3.12/Pydantic; Postgres/Supabase Auth, RLS, private storage abstraction (local in dev, R2 candidate); durable database queue with leases, retries, idempotency. Vercel front-end, Render API, separate workers for execution; free Render sleep is not a durable worker solution. Docker for portability. GPU candidates ACE-Step (verify exact license/model revision), RunPod or Modal; commercial API candidates benchmark only after access, pricing, terms and budget approval. No Railway. No Redis required for initial vertical slice.

Mock mode is explicit and only uses rights-cleared fixtures. Production refuses mock provider. Keep credentials server-side. Validate uploads and file signatures, use signed URLs, size/duration caps, ownership checks, bounded retries, rate limits and job cost reservations. All resources isolated for Synora. 
