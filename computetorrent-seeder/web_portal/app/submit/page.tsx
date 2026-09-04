"use client";

/**
 * WP-1 — Task Submission Form
 * Upload a dataset/model file, pick a task type, submit to the Tracker.
 */

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { submitTask, TaskKind } from "@/lib/api";

const TASK_KINDS: { value: TaskKind; label: string }[] = [
  { value: "preprocessing",  label: "Preprocessing" },
  { value: "inference",      label: "Inference" },
  { value: "training",       label: "Training" },
  { value: "lora",           label: "LoRA Fine-tune" },
];

export default function SubmitPage() {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);

  const [taskKind, setTaskKind] = useState<TaskKind>("inference");
  const [modelRef, setModelRef] = useState("");
  const [file, setFile]         = useState<File | null>(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) { setError("Please select a file."); return; }
    if (!modelRef.trim()) { setError("Please enter a model / dataset name."); return; }

    setLoading(true);
    setError(null);

    try {
      const res = await submitTask({ taskKind, modelRef: modelRef.trim(), file });
      router.push(`/dashboard/${res.taskId}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Submission failed.");
      setLoading(false);
    }
  }

  return (
    <div className="max-w-lg mx-auto">
      <h1 className="text-2xl font-bold mb-6">Submit a Task</h1>

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Task kind */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">Task Type</label>
          <div className="grid grid-cols-2 gap-2">
            {TASK_KINDS.map(({ value, label }) => (
              <button
                key={value}
                type="button"
                onClick={() => setTaskKind(value)}
                className={`rounded-lg border px-4 py-2 text-sm font-medium transition-colors
                  ${taskKind === value
                    ? "border-blue-500 bg-blue-600 text-white"
                    : "border-gray-600 text-gray-300 hover:border-gray-400 hover:text-white"
                  }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Model / dataset ref */}
        <div>
          <label htmlFor="modelRef" className="block text-sm font-medium text-gray-300 mb-1">
            Model / Dataset Name
          </label>
          <input
            id="modelRef"
            type="text"
            placeholder="e.g. phi-3-gguf"
            value={modelRef}
            onChange={e => setModelRef(e.target.value)}
            className="w-full rounded-lg bg-gray-800 border border-gray-600 px-3 py-2 text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
          />
        </div>

        {/* File upload */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">Dataset / Script File</label>
          <div
            className="border-2 border-dashed border-gray-600 rounded-lg p-6 text-center cursor-pointer hover:border-blue-500 transition-colors"
            onClick={() => fileRef.current?.click()}
          >
            {file ? (
              <p className="text-sm text-blue-400">{file.name} ({(file.size / 1024).toFixed(1)} KB)</p>
            ) : (
              <p className="text-sm text-gray-400">Click to select or drag & drop a file</p>
            )}
          </div>
          <input
            ref={fileRef}
            type="file"
            className="hidden"
            onChange={e => setFile(e.target.files?.[0] ?? null)}
          />
        </div>

        {error && (
          <p role="alert" className="text-sm text-red-400">{error}</p>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-blue-600 py-3 font-semibold text-white hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? "Submitting…" : "Submit Task"}
        </button>
      </form>
    </div>
  );
}
