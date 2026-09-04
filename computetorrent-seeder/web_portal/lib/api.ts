/**
 * API helpers — thin wrappers around Partner 1's Tracker/Relay REST endpoints.
 * We only know the request/response shapes, not how the Tracker is implemented.
 */

const BASE = process.env.NEXT_PUBLIC_TRACKER_URL ?? "http://localhost:8080";

export type TaskKind = "preprocessing" | "inference" | "training" | "lora";

export interface SubmitTaskRequest {
  taskKind: TaskKind;
  modelRef: string;   // name / identifier of the model or dataset
  file: File;
}

export interface SubmitTaskResponse {
  taskId: string;
  swarmId: string;
  status: string;
}

export interface TaskHistoryItem {
  taskId: string;
  taskKind: TaskKind;
  modelRef: string;
  submittedAt: string; // ISO-8601
  status: string;
  outputRef?: string;
}

/** WP-1: Submit a new task with the uploaded file. */
export async function submitTask(req: SubmitTaskRequest): Promise<SubmitTaskResponse> {
  const form = new FormData();
  form.append("taskKind", req.taskKind);
  form.append("modelRef", req.modelRef);
  form.append("file", req.file);

  const res = await fetch(`${BASE}/api/tasks`, { method: "POST", body: form });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Submit failed (${res.status}): ${text}`);
  }
  return res.json() as Promise<SubmitTaskResponse>;
}

/** WP-3 / WP-4: Fetch history of submitted tasks for this session. */
export async function fetchHistory(): Promise<TaskHistoryItem[]> {
  const res = await fetch(`${BASE}/api/tasks`);
  if (!res.ok) throw new Error(`History fetch failed (${res.status})`);
  return res.json() as Promise<TaskHistoryItem[]>;
}

/** WP-3: Fetch a single task's result details. */
export async function fetchTaskResult(taskId: string): Promise<TaskHistoryItem> {
  const res = await fetch(`${BASE}/api/tasks/${taskId}`);
  if (!res.ok) throw new Error(`Task fetch failed (${res.status})`);
  return res.json() as Promise<TaskHistoryItem>;
}
