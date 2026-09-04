"use client";

/**
 * WP-2 — Live task dashboard
 * Subscribes to Socket.io events from the Tracker and shows:
 *   - Swarm status & seeder count
 *   - Per-chunk progress bar
 *   - Current execution state
 * Redirects to /results/[taskId] when the task completes.
 */

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { getSocket, TaskStatusPayload, TaskCompletePayload } from "@/lib/socket";

interface SwarmState {
  state: TaskStatusPayload["state"];
  seederCount: number;
  chunksTotal: number;
  chunksDone: number;
}

const STATE_LABELS: Record<TaskStatusPayload["state"], string> = {
  queued:      "Queued",
  downloading: "Downloading chunks…",
  running:     "Running on seeders…",
  completed:   "Completed",
  failed:      "Failed",
};

const STATE_COLORS: Record<TaskStatusPayload["state"], string> = {
  queued:      "text-yellow-400",
  downloading: "text-blue-400",
  running:     "text-green-400",
  completed:   "text-emerald-400",
  failed:      "text-red-400",
};

export default function DashboardPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const router = useRouter();

  const [swarm, setSwarm] = useState<SwarmState>({
    state: "queued",
    seederCount: 0,
    chunksTotal: 0,
    chunksDone: 0,
  });
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const socket = getSocket();

    socket.connect();
    socket.on("connect",    () => setConnected(true));
    socket.on("disconnect", () => setConnected(false));

    // WP-2: live swarm updates
    socket.on("task:status", (payload: TaskStatusPayload) => {
      if (payload.taskId !== taskId) return;
      setSwarm({
        state:        payload.state,
        seederCount:  payload.seederCount,
        chunksTotal:  payload.chunksTotal,
        chunksDone:   payload.chunksDone,
      });
    });

    // WP-3: redirect when done
    socket.on("task:complete", (payload: TaskCompletePayload) => {
      if (payload.taskId !== taskId) return;
      router.push(`/results/${taskId}`);
    });

    return () => {
      socket.off("task:status");
      socket.off("task:complete");
      socket.disconnect();
    };
  }, [taskId, router]);

  const pct = swarm.chunksTotal > 0
    ? Math.round((swarm.chunksDone / swarm.chunksTotal) * 100)
    : 0;

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Task Dashboard</h1>
        <span className={`text-xs ${connected ? "text-green-400" : "text-gray-500"}`}>
          {connected ? "● Live" : "○ Connecting…"}
        </span>
      </div>

      <p className="text-sm text-gray-400 font-mono break-all">Task ID: {taskId}</p>

      {/* State */}
      <div className="rounded-xl bg-gray-800 border border-gray-700 p-5 space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-sm text-gray-400">Status</span>
          <span className={`font-semibold ${STATE_COLORS[swarm.state]}`}>
            {STATE_LABELS[swarm.state]}
          </span>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-sm text-gray-400">Active Seeders</span>
          <span className="font-semibold text-white">{swarm.seederCount}</span>
        </div>

        {/* Chunk progress bar */}
        {swarm.chunksTotal > 0 && (
          <div>
            <div className="flex justify-between text-xs text-gray-400 mb-1">
              <span>Chunks</span>
              <span>{swarm.chunksDone} / {swarm.chunksTotal} ({pct}%)</span>
            </div>
            <div className="w-full bg-gray-700 rounded-full h-2.5">
              <div
                className="bg-blue-500 h-2.5 rounded-full transition-all duration-300"
                style={{ width: `${pct}%` }}
                role="progressbar"
                aria-valuenow={pct}
                aria-valuemin={0}
                aria-valuemax={100}
              />
            </div>
          </div>
        )}
      </div>

      {swarm.state === "failed" && (
        <div className="rounded-lg bg-red-900/30 border border-red-700 p-4 text-sm text-red-300">
          This task failed. You can resubmit it from the{" "}
          <a href="/submit" className="underline">submission form</a>.
        </div>
      )}
    </div>
  );
}
