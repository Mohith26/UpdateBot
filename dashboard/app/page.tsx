import { fetchProperties, fetchRuns } from "@/lib/sheets";
import { JobTriggers } from "./components/JobTriggers";
import { PropertiesTable } from "./components/PropertiesTable";
import { RefreshButton } from "./components/RefreshButton";
import { RunsTable } from "./components/RunsTable";

export const revalidate = 60;
export const dynamic = "force-dynamic";

function ErrorBanner({ label, message }: { label: string; message: string }) {
  return (
    <div className="rounded border border-red-200 bg-red-50 p-3 text-red-800">
      <span className="font-medium">Could not load {label}:</span> {message}
    </div>
  );
}

export default async function Page() {
  const [runsRes, propsRes] = await Promise.all([
    fetchRuns(25),
    fetchProperties(),
  ]);
  const loadedAt = new Date();

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <header className="mb-8 flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">UpdateBot</h1>
          <p className="mt-1 text-xs text-gray-500">
            admin dashboard · loaded {loadedAt.toLocaleString()}
          </p>
        </div>
        <RefreshButton />
      </header>

      <JobTriggers />

      <section className="mb-10">
        <h2 className="mb-3 text-xs uppercase tracking-wider text-gray-500">
          Recent runs
        </h2>
        {runsRes.ok ? (
          <RunsTable runs={runsRes.data} />
        ) : (
          <ErrorBanner label="runs" message={runsRes.error} />
        )}
      </section>

      <section>
        <h2 className="mb-3 text-xs uppercase tracking-wider text-gray-500">
          Properties
        </h2>
        {propsRes.ok ? (
          <PropertiesTable properties={propsRes.data} />
        ) : (
          <ErrorBanner label="properties" message={propsRes.error} />
        )}
      </section>

      <footer className="mt-12 text-xs text-gray-400">
        Data: Google Sheets · service-account read-only · revalidate 60s.
      </footer>
    </main>
  );
}
