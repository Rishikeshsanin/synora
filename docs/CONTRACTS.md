# Integration contract v0.1 (lead-owned)

API prefix /v1. JSON UTC timestamps, UUID IDs. Bearer Supabase access token in real mode; no trust of client user IDs. Dev mocks explicitly marked. Endpoints: GET /health, GET /ready; POST /v1/music/jobs (Idempotency-Key required); GET /v1/jobs/{id}; GET /v1/assets/{id} (authorized metadata and short-lived playback/download URL). POST returns 202; errors use {code,message,request_id}. API responses must not leak credentials.

Music request: {prompt:string, mode:"instrumental"|"vocals", genres:string[], moods:string[], instruments:string[], duration_seconds:integer, bpm:integer|null, lyrics:string|null, language:string|null}. Initial duration 15-120 seconds and bpm 40-200; unsupported controls must be surfaced as capability limitations, never promised exact. Validate prompt and array bounds.

Job response: {id,status,progress,asset_id,error,created_at,updated_at,provider,simulated}; status queued|running|succeeded|failed|cancelled. Progress 0-100; asset_id nullable; error nullable {code,message}; provider nullable until routed. Only authorized owner can read. Provider failures must be visible, not replaced silently with mock. Real production must not allow simulated output. Asset metadata: {id,kind,mime_type,duration_seconds,url,expires_at,simulated}; kind audio|video|image; signed URL, nullable duration for image.

Provider contract (Python): MusicSpec matching request; capabilities; generate(spec, context) -> output artifact + provider/model revision + actual duration + provenance/cost metadata. Local fixture provider deterministic and simulated; actual providers behind explicit feature flag and budget. No secrets in results. Worker writes private asset before atomic successful transition. Durable job claims lease + attempt counter; retries bounded and idempotent. Billing reservation/settlement before commercial activation.

M2 contracts are proposals only until M1 vertical slice is verified. Media agent must document proposed brief, concept, storyboard and render contracts in its own directory; lead will ratify later.
