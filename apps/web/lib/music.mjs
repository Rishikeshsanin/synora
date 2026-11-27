export const terminal = status => ['succeeded','failed','cancelled'].includes(status);
export function musicSpec(form) {
  const prompt = form.prompt.trim();
  if (!prompt || prompt.length > 2000) throw new Error('Describe your music in 1–2000 characters.');
  const duration_seconds = Number(form.duration);
  if (!Number.isInteger(duration_seconds) || duration_seconds < 15 || duration_seconds > 120) throw new Error('Duration must be 15–120 seconds.');
  const bpm = form.bpm === '' ? null : Number(form.bpm);
  if (bpm !== null && (!Number.isInteger(bpm) || bpm < 40 || bpm > 200)) throw new Error('Tempo must be 40–200 BPM.');
  if (!['instrumental','vocals'].includes(form.mode)) throw new Error('Choose a vocal mode.');
  const lyrics = form.mode === 'vocals' ? form.lyrics.trim() || null : null;
  if (lyrics && lyrics.length > 6000) throw new Error('Lyrics must be at most 6000 characters.');
  const tags = key => {
    const values = form[key];
    if (!Array.isArray(values) || values.length > 12 || values.some(v => typeof v !== 'string' || !v.trim() || v.trim().length > 64)) throw new Error('Choose at most twelve valid ' + key + '.');
    return [...new Set(values.map(v => v.trim()))];
  };
  const language = form.mode === 'vocals' ? form.language.trim() || null : null;
  if (language && language.length > 32) throw new Error('Language must be at most 32 characters.');
  return {prompt,mode:form.mode,genres:tags('genres'),moods:tags('moods'),instruments:tags('instruments'),duration_seconds,bpm,lyrics,language};
}
export function validateJob(job) {
  if (!job || typeof job.id !== 'string' || !['queued','running','succeeded','failed','cancelled'].includes(job.status) || typeof job.progress !== 'number' || !Number.isFinite(job.progress) || job.progress < 0 || job.progress > 100 || typeof job.simulated !== 'boolean') throw new Error('Invalid job response.');
  if (job.status === 'succeeded' && typeof job.asset_id !== 'string') throw new Error('Completed job has no asset.');
  return job;
}
export function validateAsset(asset, simulated) {
  if (!asset || asset.kind !== 'audio' || typeof asset.id !== 'string' || typeof asset.url !== 'string' || typeof asset.mime_type !== 'string' || !asset.mime_type.startsWith('audio/') || asset.simulated !== simulated) throw new Error('Invalid audio asset or provenance mismatch.');
  let url;
  try { url = new URL(asset.url); } catch { throw new Error('Invalid asset URL.'); }
  if (url.username || url.password || !['https:','http:'].includes(url.protocol) || (url.protocol === 'http:' && !['localhost','127.0.0.1','[::1]'].includes(url.hostname))) throw new Error('Unsafe asset URL.');
  return asset;
}
