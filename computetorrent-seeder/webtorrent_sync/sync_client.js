/**
 * WebTorrent File Sync Client — WT-1 to WT-5
 *
 * WT-1  Join the per-task private WebTorrent swarm from the task assignment.
 * WT-2  Download assigned chunks, verifying integrity via SHA-1 piece hashing
 *       (WebTorrent's built-in verification).
 * WT-3  Resume-on-failure for interrupted downloads (re-add torrent).
 * WT-4  Leave the swarm once the result is submitted — per-task swarms only.
 * WT-5  Hand the downloaded chunk path to the sandbox as a mounted volume path
 *       only — never a raw host path outside the container workspace.
 */

'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const EventEmitter = require('events');

let WebTorrent;
try {
  WebTorrent = require('webtorrent');
} catch {
  // Allow the module to load without webtorrent installed (tests mock it).
  WebTorrent = null;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEFAULT_DOWNLOAD_DIR = process.env.CT_WEBTORRENT_DOWNLOAD_DIR
  || path.join(os.tmpdir(), 'computetorrent_chunks');

const RESUME_MAX_ATTEMPTS = parseInt(process.env.CT_WEBTORRENT_RESUME_ATTEMPTS || '3', 10);
const TORRENT_TIMEOUT_MS  = parseInt(process.env.CT_WEBTORRENT_TIMEOUT_MS || '120000', 10);

// ---------------------------------------------------------------------------
// SyncClient
// ---------------------------------------------------------------------------

class SyncClient extends EventEmitter {
  /**
   * @param {object} opts
   * @param {string} [opts.downloadDir]  Host directory for downloaded chunks.
   * @param {object} [opts._wtInstance]  Inject a mock WebTorrent instance (tests).
   */
  constructor(opts = {}) {
    super();
    this.downloadDir = opts.downloadDir || DEFAULT_DOWNLOAD_DIR;
    this._client = opts._wtInstance || (WebTorrent ? new WebTorrent() : null);
    /** @type {Map<string, object>} swarmId -> active torrent handle */
    this._activeTorrents = new Map();
  }

  // -------------------------------------------------------------------------
  // WT-1: Join swarm
  // -------------------------------------------------------------------------

  /**
   * Join the per-task swarm and begin downloading.
   *
   * @param {string} swarmId   Unique swarm ID from the task_assign message.
   * @param {string} magnetUri Magnet URI or torrent file path for this swarm.
   * @returns {Promise<string>} Resolves to the local chunk file path (WT-5).
   */
  async joinSwarm(swarmId, magnetUri) {
    if (!this._client) {
      throw new Error('WebTorrent is not available — install the webtorrent package.');
    }

    const destDir = path.join(this.downloadDir, swarmId);
    fs.mkdirSync(destDir, { recursive: true });

    this.emit('swarm:joining', { swarmId });

    return this._downloadWithRetry(swarmId, magnetUri, destDir, 0);
  }

  // -------------------------------------------------------------------------
  // WT-4: Leave swarm
  // -------------------------------------------------------------------------

  /**
   * Remove this torrent from the WebTorrent client after result submission.
   * Per-task swarms only — not seeded indefinitely.
   *
   * @param {string} swarmId
   * @returns {Promise<void>}
   */
  async leaveSwarm(swarmId) {
    const torrent = this._activeTorrents.get(swarmId);
    if (!torrent) {
      return; // already gone or never joined
    }
    return new Promise((resolve) => {
      torrent.destroy(() => {
        this._activeTorrents.delete(swarmId);
        this.emit('swarm:left', { swarmId });
        resolve();
      });
    });
  }

  // -------------------------------------------------------------------------
  // WT-4: Leave all swarms (called on app shutdown)
  // -------------------------------------------------------------------------

  async destroy() {
    if (!this._client) return;
    return new Promise((resolve) => {
      this._client.destroy(resolve);
    });
  }

  // -------------------------------------------------------------------------
  // WT-5: Validate that a chunk path is safe to mount into the sandbox
  // -------------------------------------------------------------------------

  /**
   * Return the absolute path to a downloaded chunk, confirmed to be inside
   * the managed download directory.  Throws if the path would escape it.
   *
   * The desktop app / controller passes this path to SandboxRunner as the
   * volume mount source — it must never be an arbitrary host path (WT-5).
   *
   * @param {string} swarmId
   * @param {string} filename
   * @returns {string} Safe absolute path.
   */
  resolveChunkPath(swarmId, filename) {
    const base = path.resolve(path.join(this.downloadDir, swarmId));
    const resolved = path.resolve(path.join(base, filename));
    if (!resolved.startsWith(base + path.sep) && resolved !== base) {
      throw new Error(`Path traversal detected: ${filename} escapes download directory.`);
    }
    return resolved;
  }

  // -------------------------------------------------------------------------
  // Internal: download with retry (WT-3)
  // -------------------------------------------------------------------------

  _downloadWithRetry(swarmId, magnetUri, destDir, attempt) {
    return new Promise((resolve, reject) => {
      let timer;

      const torrent = this._client.add(magnetUri, { path: destDir }, (torrent) => {
        clearTimeout(timer);
        this._activeTorrents.set(swarmId, torrent);
        this.emit('swarm:joined', { swarmId, infoHash: torrent.infoHash });
      });

      // WT-2: 'done' fires after all pieces verified by SHA-1
      torrent.on('done', () => {
        const files = torrent.files.map(f => path.join(destDir, f.path));
        this.emit('download:complete', { swarmId, files });
        resolve(files[0] || destDir);
      });

      torrent.on('error', async (err) => {
        clearTimeout(timer);
        this._activeTorrents.delete(swarmId);
        this.emit('download:error', { swarmId, attempt, err: err.message });

        // WT-3: retry up to RESUME_MAX_ATTEMPTS
        if (attempt < RESUME_MAX_ATTEMPTS) {
          try {
            const result = await this._downloadWithRetry(swarmId, magnetUri, destDir, attempt + 1);
            resolve(result);
          } catch (retryErr) {
            reject(retryErr);
          }
        } else {
          reject(new Error(`Download failed after ${attempt + 1} attempts: ${err.message}`));
        }
      });

      // Timeout guard — treat as failure, let retry logic handle it
      timer = setTimeout(() => {
        torrent.emit('error', new Error(`Torrent timeout after ${TORRENT_TIMEOUT_MS}ms`));
      }, TORRENT_TIMEOUT_MS);
    });
  }
}

module.exports = { SyncClient, DEFAULT_DOWNLOAD_DIR, RESUME_MAX_ATTEMPTS };
