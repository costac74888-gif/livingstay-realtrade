/** Exact Git Data API backup state machine; transport is injected, never credentials. */
import { createHash } from 'node:crypto';

export class BackupError extends Error {}
const fail = message => { throw new BackupError(message); };
const shaPattern = /^[a-f0-9]{40}$/;
const sha = value => typeof value === 'string' && shaPattern.test(value);
const bytes = value => Buffer.byteLength(JSON.stringify(value), 'utf8');
export const fingerprint = manifest =>
  createHash('sha256').update(JSON.stringify(manifest)).digest('hex');
const hash = (type, raw) => createHash('sha1')
  .update(`${type} ${raw.length}\0`).update(raw).digest('hex');

function identity(person) {
  if (!person || typeof person.name !== 'string' || typeof person.email !== 'string'
      || /[\n<>]/.test(person.name + person.email)) fail('Unsupported commit identity');
  const date = person.date;
  if (typeof date !== 'string' || !/^[0-9]{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$/.test(date)
      || !Number.isFinite(Date.parse(date))) fail('Unsupported commit timestamp');
  return `${person.name} <${person.email}> ${Date.parse(date) / 1000} ${date.slice(-6).replace(':', '')}`;
}

export function validateManifest(manifest, maxRequestBytes) {
  if (manifest.version !== 1 || typeof manifest.owner !== 'string'
      || typeof manifest.repository !== 'string'
      || !/^[A-Za-z0-9_-]+$/.test(manifest.owner)
      || !/^[A-Za-z0-9_.-]+$/.test(manifest.repository)
      || !/^development\/[A-Za-z0-9._/-]+$/.test(manifest.branch)
      || /(?:\.\.|\/\/|\/$|\.lock(?:\/|$))/.test(manifest.branch)
      || ![manifest.expectedDev, manifest.expectedMain, manifest.tip].every(sha)
      || !Array.isArray(manifest.boundaries) || !manifest.boundaries.includes(manifest.expectedDev)
      || manifest.boundaries.some(value => !sha(value))
      || !Array.isArray(manifest.objects)) fail('Invalid backup manifest');
  const seen = new Set();
  const commits = new Set(manifest.boundaries);
  for (const object of manifest.objects) {
    if (!sha(object.sha) || seen.has(object.sha)
        || !['blob', 'tree', 'commit'].includes(object.type)
        || typeof object.raw !== 'string') fail('Invalid/duplicate Git object');
    const raw = Buffer.from(object.raw, 'base64');
    if (raw.toString('base64') !== object.raw || hash(object.type, raw) !== object.sha)
      fail('Local object SHA mismatch');
    const payload = object.payload;
    const fields = { blob: ['content', 'encoding'], tree: ['tree'],
      commit: ['author', 'committer', 'message', 'parents', 'tree'] };
    if (!payload || Object.keys(payload).sort().join(',') !== fields[object.type].join(','))
      fail('Unsupported Git API payload fields');
    let rebuilt;
    if (object.type === 'blob') {
      if (payload.encoding !== 'base64' || payload.content !== object.raw)
        fail('Blob payload differs from original bytes');
      rebuilt = raw;
    } else if (object.type === 'tree') {
      if (!Array.isArray(payload.tree)) fail('Invalid tree');
      rebuilt = Buffer.concat(payload.tree.map(entry => {
        const kinds = { '040000': 'tree', '100644': 'blob', '100755': 'blob',
          '120000': 'blob', '160000': 'commit' };
        if (Object.keys(entry).sort().join(',') !== 'mode,path,sha,type'
            || kinds[entry.mode] !== entry.type || !sha(entry.sha)
            || typeof entry.path !== 'string' || !entry.path
            || /[\/\0]/.test(entry.path) || ['.', '..'].includes(entry.path))
          fail('Invalid tree entry');
        if (entry.type !== 'commit' && !seen.has(entry.sha))
          fail('Tree dependency missing or out of order');
        return Buffer.concat([Buffer.from(`${entry.mode.replace(/^0/, '')} ${entry.path}\0`),
          Buffer.from(entry.sha, 'hex')]);
      }));
    } else {
      if (!seen.has(payload.tree) || !Array.isArray(payload.parents)
          || payload.parents.some(parent => !sha(parent) || !commits.has(parent))
          || typeof payload.message !== 'string') fail('Commit dependency missing or out of order');
      rebuilt = Buffer.from(`tree ${payload.tree}\n`
        + payload.parents.map(parent => `parent ${parent}\n`).join('')
        + `author ${identity(payload.author)}\ncommitter ${identity(payload.committer)}\n\n`
        + payload.message);
      commits.add(object.sha);
    }
    if (!rebuilt.equals(raw)) fail('API payload cannot preserve original Git bytes');
    if (bytes(payload) > maxRequestBytes) fail('Object exceeds request byte limit; no ref update');
    seen.add(object.sha);
  }
  if (!commits.has(manifest.tip)) fail('Tip commit is absent');
  return seen;
}

/** One bounded batch. Reinvoke with saved state until phase=verified.
 * send(method,path,body) returns {status,data,isJson,retryAfter}; never return raw errors.
 * save persists state atomically after EACH verified object / ref intent / final check.
 */
export async function runBatch({ manifest, state, send, save,
  maxObjects = 20, maxBatchBytes = 512 * 1024, maxRequestBytes = 256 * 1024,
  attempts = 3, sleep = ms => new Promise(resolve => setTimeout(resolve, ms)),
  updateRef = false }) {
  if (![maxObjects, maxBatchBytes, maxRequestBytes, attempts].every(n =>
    Number.isSafeInteger(n) && n > 0) || attempts > 10
      || maxRequestBytes > maxBatchBytes) fail('Invalid bounded batch limits');
  const objects = validateManifest(manifest, maxRequestBytes);
  const id = fingerprint(manifest);
  if (state && (state.version !== 1 || state.manifest !== id
      || !['uploading', 'ready', 'ref-intent', 'verified'].includes(state.phase)
      || !Array.isArray(state.completed) || new Set(state.completed).size !== state.completed.length
      || state.completed.some(value => !objects.has(value)))) fail('Progress does not match export');
  if (state && ['ref-intent', 'verified'].includes(state.phase)
      && state.completed.length !== objects.size) fail('Incomplete ref intent');
  state = state ? structuredClone(state) :
    { version: 1, manifest: id, completed: [], phase: 'uploading' };
  const root = `/repos/${manifest.owner}/${manifest.repository}/git`;
  async function api(method, path, body, { missing = false, retry = true } = {}) {
    for (let attempt = 0; attempt < attempts; attempt++) {
      let result;
      try { result = await send(method, root + path, body); }
      catch { result = { status: 0, isJson: false }; }
      if (result.status >= 200 && result.status < 300 && result.isJson
          && result.data && typeof result.data === 'object') return result.data;
      if (missing && result.status === 404 && result.isJson) return null;
      const transient = result.status === 0 || result.status === 429
        || result.status >= 500;
      if (!retry || !transient || attempt + 1 === attempts)
        fail(`GitHub request failed (${Number.isInteger(result.status) ? result.status : 0}); progress retained`);
      const delay = Number(result.retryAfter);
      await sleep(Number.isFinite(delay) && delay > 0 ?
        Math.min(delay * 1000, 30000) : Math.min(1000 * 2 ** attempt, 30000));
    }
  }
  const refPath = branch => '/ref/heads/' + branch.split('/').map(encodeURIComponent).join('/');
  async function ref(branch) {
    const result = await api('GET', refPath(branch));
    if (result.ref !== `refs/heads/${branch}` || !sha(result.object?.sha)
        || result.object.type !== 'commit') fail('Invalid GitHub ref response');
    return result.object.sha;
  }
  async function mainUnchanged() {
    if (await ref('main') !== manifest.expectedMain) fail('Remote main changed; stopped');
  }
  await mainUnchanged();
  const current = await ref(manifest.branch);
  // Only an explicitly persisted ref intent permits recovery after a lost PATCH response.
  const recovering = ['ref-intent', 'verified'].includes(state.phase) && current === manifest.tip;
  if (current !== manifest.expectedDev && !recovering) fail('Remote development ref changed; stopped');
  if (!recovering && ['ref-intent', 'verified'].includes(state.phase)
      && current !== manifest.tip && state.phase === 'verified') fail('Verified ref changed; stopped');
  if (recovering && state.completed.length !== objects.size) fail('Incomplete ref intent');
  for (const boundary of manifest.boundaries) {
    if ((await api('GET', `/commits/${boundary}`)).sha !== boundary)
      fail('Remote boundary commit SHA mismatch');
  }
  const complete = new Set(state.completed);
  let count = 0, totalBytes = 0;
  for (const object of manifest.objects) {
    if (complete.has(object.sha)) continue;
    const size = bytes(object.payload);
    if (count >= maxObjects || totalBytes + size > maxBatchBytes) break;
    const plural = { blob: 'blobs', tree: 'trees', commit: 'commits' }[object.type];
    let result = await api('GET', `/${plural}/${object.sha}`, undefined, { missing: true });
    if (!result) {
      if (object.type === 'tree' && !object.payload.tree.length)
        fail('Empty tree unavailable remotely; no ref update');
      result = await api('POST', `/${plural}`, object.payload);
    }
    if (result.sha !== object.sha) fail('Remote object SHA mismatch; no ref update');
    complete.add(object.sha);
    state.completed.push(object.sha);
    await save(state);
    count++;
    totalBytes += size;
  }
  if (complete.size < objects.size) return { state, count, totalBytes };
  if (!['ref-intent', 'verified'].includes(state.phase)) {
    state.phase = 'ready';
    await save(state);
  }
  const tip = await api('GET', `/commits/${manifest.tip}`);
  if (tip.sha !== manifest.tip) fail('Final tip SHA mismatch');
  if (state.phase === 'ready' && !updateRef) {
    await mainUnchanged();
    return { state, count, totalBytes };
  }
  if (!recovering) {
    if (!updateRef) fail('Explicit development ref update approval required');
    await mainUnchanged();
    if (await ref(manifest.branch) !== manifest.expectedDev)
      fail('Remote development ref race; stopped');
    state.phase = 'ref-intent';
    await save(state);
    // Ref PATCH is NEVER retried blindly. A lost response is recovered on the next batch.
    const result = await api('PATCH', '/refs/heads/'
      + manifest.branch.split('/').map(encodeURIComponent).join('/'),
    { sha: manifest.tip, force: false }, { retry: false });
    if (result.ref !== `refs/heads/${manifest.branch}` || result.object?.sha !== manifest.tip)
      fail('Ref update response mismatch; verify on resume');
  }
  if (await ref(manifest.branch) !== manifest.tip) fail('Final development ref mismatch');
  await mainUnchanged();  // Last remote check, including crash recovery.
  state.phase = 'verified';
  await save(state);
  return { state, count, totalBytes };
}
