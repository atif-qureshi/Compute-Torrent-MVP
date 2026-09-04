import Link from "next/link";

export default function Home() {
  return (
    <div className="flex flex-col items-center justify-center gap-6 py-20 text-center">
      <h1 className="text-4xl font-bold text-white">
        ComputeTorrent <span className="text-blue-400">Requestor Portal</span>
      </h1>
      <p className="max-w-xl text-gray-400">
        Submit distributed ML tasks, watch them execute across the seeder
        network in real time, and download your results when they are ready.
      </p>
      <div className="flex gap-4 mt-4">
        <Link
          href="/submit"
          className="rounded-lg bg-blue-600 px-6 py-3 font-semibold text-white hover:bg-blue-500 transition-colors"
        >
          Submit a Task
        </Link>
        <Link
          href="/history"
          className="rounded-lg border border-gray-600 px-6 py-3 font-semibold text-gray-300 hover:border-gray-400 hover:text-white transition-colors"
        >
          View History
        </Link>
      </div>
    </div>
  );
}
