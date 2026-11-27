export function needsRefresh(asset, now = Date.now(), margin = 15000) {
  if (asset.url.startsWith('blob:')) return false;
  const expiry = Date.parse(asset.expires_at || '');
  return !Number.isFinite(expiry) || expiry <= now + margin;
}
export function validateSignedAsset(asset, expectedId) {
  if (asset.id !== expectedId) throw new Error('Unexpected audio asset identity.');
  if (needsRefresh(asset, Date.now(), 0)) throw new Error('Audio link is already expired or has no expiry.');
  return asset;
}
export function downloadPath(id) {
  return '/v1/assets/' + encodeURIComponent(id) + '?download=true';
}
export function fixtureLabel(simulated, local = false) {
  return simulated ? (local ? 'Local fixture · Not AI-generated' : 'Server fixture · Not AI-generated') : 'API output';
}
export function capabilityState(value) {
  if (!value || typeof value.simulated !== 'boolean') throw new Error('Unknown provider capabilities.');
  return { simulated: value.simulated, available: value.available !== false };
}
