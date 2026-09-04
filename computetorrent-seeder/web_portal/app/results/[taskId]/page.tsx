/**
 * WP-3 — Result view
 * Fetches the completed task details from the Tracker and offers a
 * download link for the merged output (provided by Partner 1's
 * Reassembly Module via outputRef).
 */

import { fetchTaskResult } from "@/lib/api";
import Link from "next/link";

interface Props {
  params: Promise<{ taskId: string }>;
}

export default async function ResultsPage({ params }: Props) {
  const { taskId } = await params;

  let task;
  let fetchError: string | null = null;

  try {
    task = await fetchTaskResult(taskId);
  } catch (err: unknown) {
    fetchError = err instanceof Error ? err.message : "Failed to load result.";
  }

  if (fetchError) {
    return (
      <div className="max-w-lg mx-auto">
        <h1 className="text-2xl font-bold mb-4">Result</h1>
        <div className="rounded-lg bg-red-900/30 border border-red-700 p-4 text-sm text-red-300">
          {fetchError}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Task Result</h1>

      <div className="rounded-xl bg-gray-800 border border-gray-700 p-5 space-y-3 text-sm">
        <Row label="Task ID"     value={task!.taskId} mono />
        <Row label="Type"        value={task!.taskKind} />
        <Row label="Model / Dataset" value={task!.modelRef} />
        <Row label="Submitted"   value={new Date(task!.submittedAt).toLocaleString()} />
        <Row label="Status"      value={task!.status} highlight />
      </div>

      {task?.outputRef ? (
        <a
          href={task.outputRef}
          download
          className="block w-full text-center rounded-lg bg-emerald-600 py-3 font-semibold text-white hover:bg-emerald-500 transition-colors"
        >
          ⬇ Download Result
        </a>
      ) : (
        <p className="text-sm text-gray-400">No output file available.</p>
      )}

      <Link href="/history" className="block text-center text-sm text-blue-400 hover:underline">
        ← Back to history
      </Link>
    </div>
  );
}

function Row({
  label,
  value,
  mono = false,
  highlight = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
  highlight?: boolean;
}) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-gray-400 shrink-0">{label}</span>
      <span className={`text-right break-all ${mono ? "font-mono text-xs" : ""} ${highlight ? "text-emerald-400 font-semibold" : "text-white"}`}>
        {value}
      </span>
    </div>
  );
}
