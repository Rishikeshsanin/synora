import {validateJob,validateAsset} from './music.mjs';
const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
/** @param {string|null} cursor */
export function libraryPath(cursor = null) {
  if (cursor !== null && !uuid(cursor)) throw new Error('Invalid library cursor.');
  return '/v1/music/library?limit=30' + (cursor === null ? '' : '&cursor=' + encodeURIComponent(cursor));
}
/** @param {any} value @param {string|null} cursor */
export function parseLibraryPage(value, cursor = null) {
  if (!value || !Array.isArray(value.items) || value.items.length > 30 || (value.next_cursor !== null && !uuid(value.next_cursor))) throw new Error('Invalid library response.');
  const seen = new Set();
  const items = value.items.map(row => {
    const job = validateJob(row?.job);
    if (!uuid(job.id) || seen.has(job.id) || job.id === cursor || typeof row.prompt !== 'string' || row.prompt.length > 2000 || !Number.isFinite(Date.parse(job.created_at))) throw new Error('Invalid library item.');
    seen.add(job.id);
    if (job.status === 'succeeded' ? !uuid(job.asset_id) : job.asset_id !== null) throw new Error('Invalid library job asset.');
    let asset = null;
    if (row.asset !== null) {
      const media = validateAsset(row.asset, job.simulated);
      if (job.status !== 'succeeded' || media.id !== job.asset_id || !Number.isFinite(media.duration_seconds) || media.duration_seconds <= 0) throw new Error('Invalid library audio metadata.');
      // Listing URLs are intentionally discarded; selection always requests fresh authorized metadata.
      asset = {id:media.id,duration_seconds:media.duration_seconds};
    }
    return {job,asset,prompt:row.prompt};
  });
  if (value.next_cursor !== null && (value.next_cursor === cursor || value.next_cursor !== items.at(-1)?.job.id)) throw new Error('Invalid library pagination.');
  return {items,next_cursor:value.next_cursor};
}
export function mergeLibraryItems(previous, incoming) {
  const result = new Map(previous.map(item => [item.job.id,item]));
  for (const item of incoming) result.set(item.job.id,item);
  return [...result.values()];
}
