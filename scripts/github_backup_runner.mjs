/** Workspace module imported ONLY inside a CodeExecution "use impure" function. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { BackupError, runBatch } from './github_backup_objects.mjs';

export async function runConnectedBatch({ connection, manifestPath, progressPath, ...limits }) {
  const manifestFile = path.resolve(manifestPath);
  const progressFile = path.resolve(progressPath);
  if (![manifestFile, progressFile].every(file =>
    file.split(path.sep).includes('generated-artifacts')) || manifestFile === progressFile)
    throw new BackupError('Use distinct ignored generated-artifacts paths');
  if (!connection?.proxyFetch) throw new BackupError('Existing GitHub proxy connection required');
  await fs.mkdir(path.dirname(progressFile), { recursive: true, mode: 0o700 });
  let lock;
  try { lock = await fs.open(progressFile + '.lock', 'wx', 0o600); }
  catch { throw new BackupError('Progress is locked; do not run concurrent batches'); }
  const temp = progressFile + '.tmp';
  try {
    const manifest = JSON.parse(await fs.readFile(manifestFile, 'utf8'));
    let state;
    try { state = JSON.parse(await fs.readFile(progressFile, 'utf8')); }
    catch (error) { if (error.code !== 'ENOENT') throw new BackupError('Invalid progress file'); }
    const save = async value => {
      await fs.writeFile(temp, JSON.stringify(value), { mode: 0o600, flag: 'w' });
      const handle = await fs.open(temp, 'r');
      try { await handle.sync(); } finally { await handle.close(); }
      await fs.rename(temp, progressFile);
      const directory = await fs.open(path.dirname(progressFile), 'r');
      try { await directory.sync(); } finally { await directory.close(); }
    };
    const send = async (method, apiPath, body) => {
      // No token extraction, credential logging, arbitrary URL, or response-body logging.
      const response = await connection.proxyFetch(apiPath, {
        method, headers: { 'Content-Type': 'application/json', Accept: 'application/vnd.github+json' },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
      let data;
      try { data = await response.json(); } catch { /* Do not retain a non-JSON error body. */ }
      return { status: response.status, data, isJson: data !== undefined,
        retryAfter: response.headers?.get('retry-after') };
    };
    const result = await runBatch({ ...limits, manifest, state, send, save });
    return { phase: result.state.phase, completed: result.state.completed.length,
      total: manifest.objects.length, batchObjects: result.count, batchBytes: result.totalBytes };
  } catch (error) {
    if (error instanceof BackupError) throw error;
    // Connector exceptions can contain authentication material; never propagate them.
    throw new BackupError('Backup interrupted; inspect local progress and resume');
  } finally {
    await lock.close();
    await fs.unlink(progressFile + '.lock');
  }
}
