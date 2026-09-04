/**
 * WP-4 — Credit / history view
 * Lists all tasks submitted in this session with their status, type, and a
 * link to the result page if completed.
 */

import { fetchHistory, TaskHistoryItem } from "@/lib/api";
import Link from "next/link";

const STATUS_COLORS: Record<string, string> = {
  completed: "text-emerald-400",
  failed:    "text-red-400",
  running:   "text-green-400",
  queued:    "text-yellow-400",
  downloading: "text-blue-400",
};

export default async function HistoryPage() {
  let items: TaskHistoryItem[] = [];
  let fetchError: string | null = null;

  try {
    items = await fetchHistory();
  } catch (err: unknown) {
    fetchError = err instanceof Error ? err.message : "Failed to load history.";
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Task History</h1>

      {fetchError && (
        <div className="rounded-lg bg-red-900/30 border border-red-700 p-4 text-sm text-red-300">
          {fetchError}
        </div>
      )}

      {!fetchError && items.length === 0 && (
        <div className="text-gray-400 text-sm py-12 text-center">
          No tasks yet.{" "}
          <Link href="/submit" className="text-blue-400 hover:underline">
            Submit your first task →
          </Link>
        </div>
      )}

      {items.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-gray-700">
          <table className="w-full text-sm">
            <thead className="bg-gray-800 text-gray-400">
              <tr>
                <th className="text-left px-4 py-3">Task ID</th>
                <th className="text-left px-4 py-3">Type</th>
                <th className="text-left px-4 py-3">Model / Dataset</th>
                <th className="text-left px-4 py-3">Submitted</th>
                <th className="text-left px-4 py-3">Status</th>
                <th className="text-left px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {items.map(item => (
                <tr key={item.taskId} className="hover:bg-gray-800/50 transition-colors">
                  <td className="px-4 py-3 font-mono text-xs text-gray-300 max-w-[120px] truncate">
                    {item.taskId}
                  </td>
                  <td className="px-4 py-3 capitalize text-gray-200">{item.taskKind}</td>
                  <td className="px-4 py-3 text-gray-200">{item.modelRef}</td>
                  <td className="px-4 py-3 text-gray-400 whitespace-nowrap">
                    {new Date(item.submittedAt).toLocaleString()}
                  </td>
                  <td className={`px-4 py-3 font-medium ${STATUS_COLORS[item.status] ?? "text-gray-300"}`}>
                    {item.status}
                  </td>
                  <td className="px-4 py-3">
                    {item.status === "completed" ? (
                      <Link
                        href={`/results/${item.taskId}`}
                        className="text-blue-400 hover:underline text-xs"
                      >
                        View result
                      </Link>
                    ) : (
                      <Link
                        href={`/dashboard/${item.taskId}`}
                        className="text-gray-400 hover:text-white text-xs"
                      >
                        Track
                      </Link>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
