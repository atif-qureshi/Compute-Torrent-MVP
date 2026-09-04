/**
 * Tests for the WebTorrent Sync Client (WT-1 to WT-5).
 *
 * WebTorrent is mocked so these tests run on any machine without a real
 * torrent swarm.  Integration tests (real swarm) are skipped unless
 * CT_INTEGRATION_TEST=1 is set.
 */

'use strict';

const assert = require('assert');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { test, describe, before, after } = require('node:test');

const { SyncClient, RESUME_MAX_ATTEMPTS } = require('../sync_client');

// ---------------------------------------------------------------------------
// Mock WebTorrent factory
// ---------------------------------------------------------------------------

/**
 * Creates a minimal mock WebTorrent instance.
 * @param {object} opts
 * @param {boolean} [opts.failFirst]     Emit 'error' on first add, succeed on retry.
 * @param {boolean} [opts.alwaysFail]    Always emit 'error'.
 * @param {string}  [opts.fileName]      Filename reported by the fake torrent.
 */
function makeMockWT(opts = {}) {
  const { failFirst = false, alwaysFail = false, fileName = 'chunk.bin' } = opts;
  let callCount = 0;

  const instance = {
    _destroyed: false,
    add(magnetUri, options, readyCb) {
      callCount++;
      const shouldFail = alwaysFail || (failFirst && callCount === 1);

      // Fake torrent object
      const fakeTorrent = {
        infoHash: 'fakehash',
        files: [{ path: fileName, name: fileName }],
        _handlers: {},
        on(event, cb) { this._handlers[event] = cb; return this; },
        emit(event, ...args) { if (this._handlers[event]) this._handlers[event](...args); },
        destroy(cb) { if (cb) cb(); },
      };

      // Fire ready callback (simulates torrent metadata ready)
      if (readyCb) setImmediate(() => readyCb(fakeTorrent));

      // Simulate download outcome
      setImmediate(() => {
        if (shouldFail) {
          fakeTorrent.emit('error', new Error('simulated download error'));
        } else {
          // Write a dummy file so the resolved path exists
          const dest = path.join(options.path, fileName);
          fs.mkdirSync(options.path, { recursive: true });
          fs.writeFileSync(dest, 'fake chunk data');
          fakeTorrent.emit('done');
        }
      });

      return fakeTorrent;
    },
    destroy(cb) { this._destroyed = true; if (cb) cb(); },
  };

  return instance;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeTmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'ct_test_'));
}

// ---------------------------------------------------------------------------
// WT-1 + WT-2: joinSwarm resolves with a file path after download
// ---------------------------------------------------------------------------

test('WT-1/WT-2: joinSwarm resolves with a local file path', async () => {
  const tmp = makeTmpDir();
  const client = new SyncClient({ downloadDir: tmp, _wtInstance: makeMockWT() });

  const result = await client.joinSwarm('swarm_001', 'magnet:?fake');
  assert.ok(typeof result === 'string', 'result should be a string path');
  assert.ok(result.startsWith(tmp), 'path should be inside download dir');
});

// ---------------------------------------------------------------------------
// WT-2: downloaded file actually exists on disk
// ---------------------------------------------------------------------------

test('WT-2: downloaded chunk file exists on disk after joinSwarm', async () => {
  const tmp = makeTmpDir();
  const client = new SyncClient({ downloadDir: tmp, _wtInstance: makeMockWT({ fileName: 'model_chunk.bin' }) });

  const filePath = await client.joinSwarm('swarm_002', 'magnet:?fake');
  assert.ok(fs.existsSync(filePath), `Expected file at ${filePath}`);
});

// ---------------------------------------------------------------------------
// WT-3: resume-on-failure retries after first error
// ---------------------------------------------------------------------------

test('WT-3: retries download after first failure', async () => {
  const tmp = makeTmpDir();
  const client = new SyncClient({
    downloadDir: tmp,
    _wtInstance: makeMockWT({ failFirst: true }),
  });

  // failFirst = fail once then succeed — should resolve after retry
  const result = await client.joinSwarm('swarm_003', 'magnet:?fake');
  assert.ok(typeof result === 'string');
});

// ---------------------------------------------------------------------------
// WT-3: exhausting retries rejects with an error
// ---------------------------------------------------------------------------

test('WT-3: rejects after exhausting all retry attempts', async () => {
  const tmp = makeTmpDir();
  const client = new SyncClient({
    downloadDir: tmp,
    _wtInstance: makeMockWT({ alwaysFail: true }),
  });

  await assert.rejects(
    () => client.joinSwarm('swarm_004', 'magnet:?fake'),
    /failed after/,
    'Should reject with retry exhaustion message'
  );
});

// ---------------------------------------------------------------------------
// WT-4: leaveSwarm removes torrent from active map
// ---------------------------------------------------------------------------

test('WT-4: leaveSwarm removes torrent from active map', async () => {
  const tmp = makeTmpDir();
  const client = new SyncClient({ downloadDir: tmp, _wtInstance: makeMockWT() });

  await client.joinSwarm('swarm_005', 'magnet:?fake');
  assert.ok(client._activeTorrents.has('swarm_005'), 'torrent should be tracked');

  await client.leaveSwarm('swarm_005');
  assert.ok(!client._activeTorrents.has('swarm_005'), 'torrent should be removed after leave');
});

// ---------------------------------------------------------------------------
// WT-4: leaveSwarm on unknown swarmId does not throw
// ---------------------------------------------------------------------------

test('WT-4: leaveSwarm on unknown swarmId is a no-op', async () => {
  const client = new SyncClient({ downloadDir: os.tmpdir(), _wtInstance: makeMockWT() });
  // Should not throw
  await client.leaveSwarm('nonexistent_swarm');
});

// ---------------------------------------------------------------------------
// WT-5: resolveChunkPath returns correct absolute path
// ---------------------------------------------------------------------------

test('WT-5: resolveChunkPath returns absolute path inside download dir', () => {
  const tmp = makeTmpDir();
  const client = new SyncClient({ downloadDir: tmp, _wtInstance: makeMockWT() });

  const resolved = client.resolveChunkPath('swarm_006', 'chunk7.bin');
  const expected = path.resolve(path.join(tmp, 'swarm_006', 'chunk7.bin'));
  assert.strictEqual(resolved, expected);
});

// ---------------------------------------------------------------------------
// WT-5: resolveChunkPath rejects path traversal
// ---------------------------------------------------------------------------

test('WT-5: resolveChunkPath throws on path traversal attempt', () => {
  const tmp = makeTmpDir();
  const client = new SyncClient({ downloadDir: tmp, _wtInstance: makeMockWT() });

  assert.throws(
    () => client.resolveChunkPath('swarm_007', '../../etc/passwd'),
    /Path traversal/,
    'Should throw on path traversal'
  );
});

// ---------------------------------------------------------------------------
// WT-1: swarm:joining and swarm:joined events are emitted
// ---------------------------------------------------------------------------

test('WT-1: emits swarm:joining and swarm:joined events', async () => {
  const tmp = makeTmpDir();
  const client = new SyncClient({ downloadDir: tmp, _wtInstance: makeMockWT() });

  const events = [];
  client.on('swarm:joining', e => events.push({ type: 'joining', ...e }));
  client.on('swarm:joined',  e => events.push({ type: 'joined',  ...e }));

  await client.joinSwarm('swarm_008', 'magnet:?fake');

  assert.ok(events.some(e => e.type === 'joining' && e.swarmId === 'swarm_008'));
  assert.ok(events.some(e => e.type === 'joined'  && e.swarmId === 'swarm_008'));
});

// ---------------------------------------------------------------------------
// destroy() calls WebTorrent destroy
// ---------------------------------------------------------------------------

test('destroy() tears down the WebTorrent client', async () => {
  const mockWT = makeMockWT();
  const client = new SyncClient({ downloadDir: os.tmpdir(), _wtInstance: mockWT });
  await client.destroy();
  assert.ok(mockWT._destroyed, 'WebTorrent client should be destroyed');
});
