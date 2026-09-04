/**
 * Node.js bridge server — reads JSON-RPC requests from stdin, dispatches
 * to SyncClient, writes JSON responses to stdout.
 *
 * Stdin/stdout are newline-delimited JSON. See bridge.py for protocol spec.
 */

'use strict';

const readline = require('readline');
const { SyncClient } = require('./sync_client');

const client = new SyncClient();

const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });

rl.on('line', async (line) => {
  let req;
  try {
    req = JSON.parse(line);
  } catch {
    return; // ignore malformed input
  }

  const { id, method, params } = req;

  if (method === 'shutdown') {
    await client.destroy();
    process.exit(0);
  }

  try {
    let result;
    if (method === 'joinSwarm') {
      result = await client.joinSwarm(params.swarmId, params.magnetUri);
    } else if (method === 'leaveSwarm') {
      await client.leaveSwarm(params.swarmId);
      result = 'ok';
    } else if (method === 'resolveChunkPath') {
      result = client.resolveChunkPath(params.swarmId, params.filename);
    } else {
      throw new Error(`Unknown method: ${method}`);
    }
    process.stdout.write(JSON.stringify({ id, result }) + '\n');
  } catch (err) {
    process.stdout.write(JSON.stringify({ id, error: err.message }) + '\n');
  }
});
