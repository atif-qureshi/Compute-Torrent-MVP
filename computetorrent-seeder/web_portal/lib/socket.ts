/**
 * Socket.io client singleton — WP-2
 *
 * Connects to Partner 1's Tracker/Relay which emits:
 *   "task:status"   { taskId, state, seederCount, chunksTotal, chunksDone }
 *   "task:complete" { taskId, outputRef }
 *
 * We treat the Tracker as a black box — we only know these event names
 * and their payload shapes (NFR-5).
 */

import { io, Socket } from "socket.io-client";

const TRACKER_URL =
  process.env.NEXT_PUBLIC_TRACKER_URL ?? "http://localhost:8080";

let socket: Socket | null = null;

export function getSocket(): Socket {
  if (!socket) {
    socket = io(TRACKER_URL, {
      autoConnect: false,
      transports: ["websocket"],
    });
  }
  return socket;
}

// ---- Typed event payloads ------------------------------------------------

export interface TaskStatusPayload {
  taskId: string;
  state: "queued" | "downloading" | "running" | "completed" | "failed";
  seederCount: number;
  chunksTotal: number;
  chunksDone: number;
}

export interface TaskCompletePayload {
  taskId: string;
  outputRef: string; // URL or path returned by Partner 1's Reassembly Module
}
