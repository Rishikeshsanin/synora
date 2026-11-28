// Interpret only the existing capability response; absence is not authorization.
const identifier = value => typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$/.test(value) ? value : null;
/** @param {any} value */
export function providerStatus(value) {
  if (!value || typeof value.simulated !== 'boolean' || typeof value.available !== 'boolean') throw new Error('Unknown provider capabilities.');
  const provider=identifier(value.provider), model=identifier(value.model), revision=identifier(value.revision);
  const fixedDuration=Number.isInteger(value.fixed_duration)&&value.fixed_duration>=15&&value.fixed_duration<=120?Number(value.fixed_duration):null;
  const available=value.available&&(value.simulated||Boolean(provider&&model&&revision));
  return {available,simulated:value.simulated,provider,model,revision,fixedDuration};
}
/** @typedef {ReturnType<typeof providerStatus>} ProviderStatus */
/** @param {ProviderStatus|null} status @param {boolean} demo @param {{mode:string,duration_seconds:number}} spec */
export function generationBlock(status,demo,spec) {
  if (demo) return '';
  if (!status) return 'Provider status is unknown. Refresh status before generating.';
  if (!status.available) return 'No approved provider is available. You can use the explicit local demo.';
  if (!status.simulated && spec.mode==='vocals') return 'Genuine vocal and lyric quality is not verified for any language in this integration. Choose Instrumental or use the explicit local demo.';
  if (status.fixedDuration!==null && spec.duration_seconds!==status.fixedDuration) return 'This provider requires '+status.fixedDuration+' seconds.';
  return '';
}
/** @param {ProviderStatus|null} status @param {boolean} demo @param {string} language */
export function vocalNotice(status,demo,language) {
  if (demo || status?.simulated) return 'Fixture only: lyrics and '+language+' vocals are not generated.';
  return language+' singing and lyric adherence are unverified. A playable audio file does not prove vocal or language quality.';
}
/** @param {string} language */
export function lyricLocale(language) {
  return ({English:'en',Hindi:'hi',Telugu:'te',Tamil:'ta',Kannada:'kn',Spanish:'es',French:'fr',Japanese:'ja'})[language] || undefined;
}
/** @param {ProviderStatus} first @param {ProviderStatus} next */
export function sameProvider(first,next) {
  return first.available===next.available&&first.simulated===next.simulated&&first.provider===next.provider&&first.model===next.model&&first.revision===next.revision&&first.fixedDuration===next.fixedDuration;
}
/** @param {boolean} simulated @param {boolean} [local] */
export function outputProvenance(simulated,local=false) {
  return simulated?(local?'Local fixture · Not AI-generated':'Server fixture · Not AI-generated'):'Non-fixture API output · Quality unverified';
}
