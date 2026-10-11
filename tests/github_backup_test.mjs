/** Offline only: disposable Git repository + virtual GitHub/proxy responses. */
import assert from 'node:assert/strict';
import { test, after } from 'node:test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { runBatch, validateManifest, fingerprint } from '../scripts/github_backup_objects.mjs';
import { runConnectedBatch } from '../scripts/github_backup_runner.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'github-backup-test-'));
after(() => fs.rm(temp, { recursive: true, force: true }));
const repo = path.join(temp, 'repo');
await fs.mkdir(repo);
function git(...args) {
  return execFileSync('git', ['-C', repo, ...args], { encoding: 'utf8',
    env: { ...process.env, GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_GLOBAL: '/dev/null',
      GIT_AUTHOR_NAME: 'Original Author', GIT_AUTHOR_EMAIL: 'author@example.invalid',
      GIT_COMMITTER_NAME: 'Other Committer', GIT_COMMITTER_EMAIL: 'committer@example.invalid',
      GIT_AUTHOR_DATE: '2025-01-02T03:04:05+09:00',
      GIT_COMMITTER_DATE: '2025-02-03T04:05:06-03:30' } }).trim();
}
git('init', '-q');
await fs.writeFile(path.join(repo, 'delete.txt'), 'old\n');
git('add', '.'); git('commit', '-qm', 'base');
const base = git('rev-parse', 'HEAD');
await fs.unlink(path.join(repo, 'delete.txt'));
await fs.mkdir(path.join(repo, 'nested'));
await fs.writeFile(path.join(repo, 'nested', '한글.txt'), '원문\r\n\n');
await fs.writeFile(path.join(repo, 'binary.bin'), Buffer.from([0, 255, 128, 10]));
await fs.writeFile(path.join(repo, 'run.sh'), '#!/bin/sh\n');
await fs.chmod(path.join(repo, 'run.sh'), 0o755);
await fs.symlink('nested/한글.txt', path.join(repo, 'link'));
git('add', '.'); git('commit', '-qm', '내용\n\n마지막 줄\n');
const changed = git('rev-parse', 'HEAD');
git('commit', '--allow-empty', '-qm', 'empty commit preserved');
const empty = git('rev-parse', 'HEAD');
git('checkout', '-qb', 'side', base);
await fs.writeFile(path.join(repo, 'side.txt'), 'side\n');
git('add', '.'); git('commit', '-qm', 'side parent');
const side = git('rev-parse', 'HEAD');
git('checkout', '-q', '-');
git('merge', '--no-ff', '-qm', 'merge parents preserved', side);
const tip = git('rev-parse', 'HEAD');
const manifestFile = path.join(temp, 'generated-artifacts', 'export.json');
execFileSync('python', [path.join(root, 'scripts/github_backup_export.py'),
  '--repo', repo, '--base', base, '--tip', tip, '--owner', 'example',
  '--repository', 'backup', '--branch', 'development/backup',
  '--expected-main', base, '--output', manifestFile]);
const manifest = JSON.parse(await fs.readFile(manifestFile, 'utf8'));

function digest(type, content) {
  return createHash('sha1').update(Buffer.concat([
    Buffer.from(type + ' ' + content.length + '\0'), content])).digest('hex');
}
function payloadBytes(type, payload) {
  if (type === 'blob') return Buffer.from(payload.content, payload.encoding);
  if (type === 'tree') return Buffer.concat(payload.tree.map(e => Buffer.concat([
    Buffer.from(`${Number(e.mode)} ${e.path}\0`), Buffer.from(e.sha, 'hex')])));
  const person = p => `${p.name} <${p.email}> ${new Date(p.date).getTime() / 1000} `
    + p.date.substring(p.date.length - 6).split(':').join('');
  return Buffer.from([`tree ${payload.tree}`, ...payload.parents.map(p => `parent ${p}`),
    `author ${person(payload.author)}`, `committer ${person(payload.committer)}`, '',
    payload.message].join('\n'));
}
class GitHub {
  constructor() {
    this.dev = base; this.main = base; this.calls = []; this.posts = [];
    this.objects = new Map([[base, { sha: base }]]);
    this.hook = null;
  }
  send = async (method, url, payload) => {
    const call = { method, url, payload };
    this.calls.push(call);
    const intercepted = await this.hook?.(call, this);
    if (intercepted) return intercepted;
    if (url.includes('/ref/heads/')) {
      const branch = url.split('/ref/heads/')[1];
      return { status: 200, isJson: true,
        data: { ref: 'refs/heads/' + branch, object: { type: 'commit',
          sha: branch === 'main' ? this.main : this.dev } } };
    }
    if (method === 'PATCH') {
      assert.equal(url, '/repos/example/backup/git/refs/heads/development/backup');
      assert.equal(payload.force, false);
      if (this.dev !== base) return { status: 422, isJson: true, data: {} };
      this.dev = payload.sha;
      return { status: 200, isJson: true, data: { ref: 'refs/heads/development/backup',
        object: { type: 'commit', sha: this.dev } } };
    }
    if (method === 'GET') {
      const data = this.objects.get(url.split('/').at(-1));
      return { status: data ? 200 : 404, isJson: true, data: data ?? {} };
    }
    assert.equal(method, 'POST');
    const type = { blobs: 'blob', trees: 'tree', commits: 'commit' }[url.split('/').at(-1)];
    const sha = digest(type, payloadBytes(type, payload));
    const data = { sha };
    this.posts.push({ type, sha, payload });
    this.objects.set(sha, data);
    return { status: 201, isJson: true, data };
  };
}
function job(server, options = {}) {
  let saved;
  return {
    get state() { return saved; },
    run: more => runBatch({ manifest, state: saved, send: server.send,
      save: async s => { saved = structuredClone(s); }, sleep: async () => {},
      ...options, ...more }),
  };
}

test('exact Git bytes: binary, nested UTF8, executable, symlink, delete, empty and merge commits', () => {
  validateManifest(manifest, 262144);
  const commits = manifest.objects.filter(o => o.type === 'commit');
  assert.equal(commits.length, 4);
  assert.equal(commits.find(o => o.sha === empty).payload.tree,
    commits.find(o => o.sha === changed).payload.tree);
  assert.deepEqual(commits.find(o => o.sha === tip).payload.parents, [empty, side]);
  for (const object of manifest.objects) {
    assert.deepEqual(payloadBytes(object.type, object.payload), Buffer.from(object.raw, 'base64'));
    assert.equal(digest(object.type, payloadBytes(object.type, object.payload)), object.sha);
  }
  assert.ok(commits.every(o => o.payload.message.endsWith('\n')));
  assert.ok(commits.every(o => o.payload.author.date.endsWith('+09:00')
    && o.payload.committer.date.endsWith('-03:30')));
  const modes = manifest.objects.filter(o => o.type === 'tree')
    .flatMap(o => o.payload.tree.map(e => e.mode));
  for (const mode of ['040000', '100755', '120000']) assert.ok(modes.includes(mode));
});

test('bounded batches resume saved receipts, no duplicates, explicit ref update, main checked last', async () => {
  const server = new GitHub(); const work = job(server, { maxObjects: 2 });
  let result;
  do {
    result = await work.run();
    assert.ok(result.count <= 2);
    assert.ok(result.totalBytes <= 524288);
  } while (result.state.phase === 'uploading');
  assert.equal(server.dev, base);
  assert.equal(work.state.phase, 'ready');
  await work.run({ updateRef: true });
  assert.equal(work.state.phase, 'verified');
  assert.equal(server.dev, tip); assert.equal(server.main, base);
  assert.equal(new Set(server.posts.map(o => o.sha)).size, server.posts.length);
  assert.ok(server.posts.some(o => o.sha === empty));
  assert.ok(server.calls.at(-1).url.endsWith('/ref/heads/main'));
  const patches = server.calls.filter(c => c.method === 'PATCH').length;
  await work.run();
  assert.equal(server.calls.filter(c => c.method === 'PATCH').length, patches);
});

test('interruption after object creation resumes by GET and does not duplicate a POST', async () => {
  const server = new GitHub();
  let saved, stop = true;
  const options = { manifest, send: server.send, sleep: async () => {},
    save: async s => { if (stop) { stop = false; throw new Error('simulated disk interruption'); }
      saved = structuredClone(s); } };
  await assert.rejects(runBatch(options), /disk interruption/);
  assert.equal(server.posts.length, 1);
  await runBatch({ ...options, state: saved, updateRef: true });
  assert.equal(server.dev, tip);
  assert.equal(server.posts.filter(o => o.sha === manifest.objects[0].sha).length, 1);
});

test('non-JSON 403 is sanitized and stops; receipts survive for the next batch', async () => {
  const server = new GitHub(); const work = job(server);
  let posts = 0;
  server.hook = call => call.method === 'POST' && ++posts === 2
    ? { status: 403, isJson: false, data: 'PRIVATE_TOKEN_SHOULD_NOT_LEAK' } : null;
  await assert.rejects(work.run({ updateRef: true }), error =>
    !error.message.includes('PRIVATE_TOKEN') && /403/.test(error.message));
  assert.equal(work.state.completed.length, 1); assert.equal(server.dev, base);
  server.hook = null;
  await work.run({ updateRef: true });
  assert.equal(server.dev, tip);
});

test('bounded transient retries (429, non-JSON 503, transport interruption)', async () => {
  for (const status of [429, 503, 0]) {
    const server = new GitHub(); const work = job(server);
    let failures = 0;
    server.hook = call => {
      if (call.method === 'POST' && failures++ < 2) {
        if (!status) throw new Error('secret-bearing transport exception');
        return { status, isJson: false, retryAfter: 1 };
      }
    };
    await work.run({ updateRef: true });
    assert.equal(server.dev, tip);
  }
  const server = new GitHub();
  server.hook = call => call.method === 'POST' ? { status: 503, isJson: false } : null;
  await assert.rejects(job(server).run(), /503/);
  assert.equal(server.calls.filter(c => c.method === 'POST').length, 3);
  assert.equal(server.dev, base);
});

test('remote SHA mismatch and local corruption stop before any ref change', async () => {
  const server = new GitHub();
  server.hook = call => call.method === 'POST'
    ? { status: 201, isJson: true, data: { sha: 'f'.repeat(40) } } : null;
  await assert.rejects(job(server).run({ updateRef: true }), /SHA mismatch/);
  assert.equal(server.dev, base);
  const bad = structuredClone(manifest);
  bad.objects.find(o => o.type === 'commit').payload.message =
    bad.objects.find(o => o.type === 'commit').payload.message.trimEnd();
  const unused = new GitHub();
  await assert.rejects(runBatch({ manifest: bad, send: unused.send, save: async () => {} }),
    /original Git bytes/);
  assert.equal(unused.calls.length, 0);
});

test('unexpected initial ref, pre-PATCH ref race and main change all close the gate', async () => {
  let server = new GitHub(); server.dev = 'f'.repeat(40);
  await assert.rejects(job(server).run({ updateRef: true }), /development ref changed/);
  assert.equal(server.posts.length, 0);
  server = new GitHub();
  let refs = 0;
  server.hook = call => {
    if (call.url.endsWith('/ref/heads/development/backup') && ++refs === 2)
      server.dev = 'f'.repeat(40);
  };
  await assert.rejects(job(server).run({ updateRef: true }), /ref race/);
  assert.ok(!server.calls.some(c => c.method === 'PATCH'));
  server = new GitHub(); server.main = 'e'.repeat(40);
  await assert.rejects(job(server).run(), /main changed/);
  assert.equal(server.posts.length, 0);
});

test('race after precheck: non-fast-forward rejected without force retry', async () => {
  const server = new GitHub();
  server.hook = call => { if (call.method === 'PATCH') server.dev = 'f'.repeat(40); };
  await assert.rejects(job(server).run({ updateRef: true }), /422/);
  assert.equal(server.calls.filter(c => c.method === 'PATCH').length, 1);
  assert.equal(server.main, base);
});

test('lost PATCH response resumes ref intent, verifies main without repatching', async () => {
  const server = new GitHub(); const work = job(server);
  server.hook = call => {
    if (call.method === 'PATCH') { server.dev = tip; throw new Error('lost response'); }
  };
  await assert.rejects(work.run({ updateRef: true }), /failed \(0\)/);
  assert.equal(work.state.phase, 'ref-intent');
  server.hook = null;
  await work.run();
  assert.equal(work.state.phase, 'verified');
  assert.equal(server.calls.filter(c => c.method === 'PATCH').length, 1);
  assert.ok(server.calls.at(-1).url.endsWith('/ref/heads/main'));
});

test('main changes after PATCH: no success record and cannot repair main', async () => {
  const server = new GitHub(); const work = job(server);
  server.hook = call => { if (call.method === 'PATCH') server.main = 'e'.repeat(40); };
  await assert.rejects(work.run({ updateRef: true }), /main changed/);
  assert.equal(work.state.phase, 'ref-intent');
  assert.ok(!server.calls.some(c => c.method === 'PATCH' && c.url.endsWith('/main')));
});

test('byte limits, wrong journal, forbidden main branch fail before network', async () => {
  const server = new GitHub();
  await assert.rejects(job(server, { maxRequestBytes: 50 }).run(), /byte limit/);
  assert.equal(server.calls.length, 0);
  const bad = { version: 1, manifest: 'wrong', completed: [], phase: 'uploading' };
  await assert.rejects(runBatch({ manifest, state: bad, send: server.send,
    save: async () => {} }), /Progress/);
  const forbidden = { ...manifest, branch: 'main' };
  await assert.rejects(runBatch({ manifest: forbidden, send: server.send,
    save: async () => {} }), /Invalid backup manifest/);
  assert.equal(server.calls.length, 0);
  const work = job(server, { maxRequestBytes: 1024, maxBatchBytes: 1024 });
  const result = await work.run();
  assert.ok(result.totalBytes <= 1024);
  assert.equal(result.state.manifest, fingerprint(manifest));
});

test('runner uses injected existing proxy, atomic private journal, lock and sanitized errors', async () => {
  const server = new GitHub();
  const connection = { proxyFetch: async (url, init) => {
    const response = await server.send(init.method, url,
      init.body === undefined ? undefined : JSON.parse(init.body));
    return { status: response.status, headers: { get: () => null },
      json: async () => response.data };
  } };
  const progressPath = path.join(temp, 'generated-artifacts', 'progress.json');
  const args = { connection, manifestPath: manifestFile, progressPath, maxObjects: 2 };
  let result;
  do { result = await runConnectedBatch(args); } while (result.phase === 'uploading');
  assert.equal(result.phase, 'ready');
  assert.equal((await fs.stat(progressPath)).mode & 0o777, 0o600);
  const journal = await fs.readFile(progressPath, 'utf8');
  assert.ok(!journal.includes('message') && !journal.includes('email'));
  await fs.writeFile(progressPath + '.lock', '');
  await assert.rejects(runConnectedBatch(args), /locked/);
  await fs.unlink(progressPath + '.lock');
  result = await runConnectedBatch({ ...args, updateRef: true });
  assert.equal(result.phase, 'verified');
  connection.proxyFetch = async () => { throw new Error('PRIVATE_TOKEN'); };
  await assert.rejects(runConnectedBatch(args), error => !error.message.includes('PRIVATE_TOKEN'));
  await assert.rejects(fs.stat(progressPath + '.lock'), { code: 'ENOENT' });
});

test('raw commit without trailing LF is preserved; empty remote tree is reused, never POSTed', async () => {
  const emptyTree = git('hash-object', '-t', 'tree', '-w', '--stdin');
  const template = manifest.objects.find(o => o.type === 'commit').payload;
  const payload = { ...template, tree: emptyTree, parents: [base], message: 'no final LF' };
  const raw = payloadBytes('commit', payload);
  const newTip = execFileSync('git', ['-C', repo, 'hash-object', '-t', 'commit', '-w', '--stdin'],
    { input: raw, encoding: 'utf8' }).trim();
  const output = path.join(temp, 'generated-artifacts', 'empty-tree.json');
  execFileSync('python', [path.join(root, 'scripts/github_backup_export.py'),
    '--repo', repo, '--base', base, '--tip', newTip, '--owner', 'example',
    '--repository', 'backup', '--branch', 'development/backup',
    '--expected-main', base, '--output', output]);
  const exported = JSON.parse(await fs.readFile(output, 'utf8'));
  assert.equal(exported.objects.at(-1).payload.message, 'no final LF');
  const server = new GitHub();
  await assert.rejects(runBatch({ manifest: exported, send: server.send, save: async () => {},
    updateRef: true }), /Empty tree unavailable/);
  assert.equal(server.posts.length, 0);
  server.objects.set(emptyTree, { sha: emptyTree });
  const result = await runBatch({ manifest: exported, send: server.send, save: async () => {},
    updateRef: true });
  assert.equal(result.state.phase, 'verified');
  assert.equal(server.dev, newTip);
  assert.ok(!server.posts.some(o => o.type === 'tree'));
});

test('unsupported signed commit export is rejected without creating a partial manifest', async () => {
  const original = Buffer.from(manifest.objects.find(o => o.type === 'commit').raw, 'base64')
    .toString('utf8');
  const signed = original.replace('\n\n', '\ngpgsig unsupported-signature\n\n');
  const signedTip = execFileSync('git', ['-C', repo, 'hash-object', '-t', 'commit', '-w', '--stdin'],
    { input: signed, encoding: 'utf8' }).trim();
  const output = path.join(temp, 'generated-artifacts', 'unsupported.json');
  assert.throws(() => execFileSync('python', [path.join(root, 'scripts/github_backup_export.py'),
    '--repo', repo, '--base', base, '--tip', signedTip, '--owner', 'example',
    '--repository', 'backup', '--branch', 'development/backup',
    '--expected-main', base, '--output', output], { stdio: 'pipe' }),
  /Command failed/);
  await assert.rejects(fs.stat(output), { code: 'ENOENT' });
});

test('unexpected API payload flags cannot bypass hashing or change SHA via server options', async () => {
  const bad = structuredClone(manifest);
  bad.objects.find(o => o.type === 'commit').payload.signature = 'unsupported';
  const server = new GitHub();
  await assert.rejects(runBatch({ manifest: bad, send: server.send, save: async () => {} }),
    /Unsupported Git API payload fields/);
  assert.equal(server.calls.length, 0);
});
