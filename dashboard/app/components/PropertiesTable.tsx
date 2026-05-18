import type { Property } from "@/lib/sheets";
import { formatLocal, isStale, relativeTime } from "@/lib/time";

export function PropertiesTable({ properties }: { properties: Property[] }) {
  if (properties.length === 0) {
    return (
      <div className="rounded border border-dashed border-gray-300 bg-white p-6 text-gray-500">
        No properties configured. Add a row to the config sheet with at minimum:
        property_name (col A), slack_channel_id (col B), live_doc_id (col C).
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded border border-gray-200 bg-white">
      <table className="w-full text-left">
        <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
          <tr>
            <th className="px-3 py-2 font-normal">Property</th>
            <th className="px-3 py-2 font-normal">Last sync</th>
            <th className="px-3 py-2 font-normal">Live doc</th>
          </tr>
        </thead>
        <tbody>
          {properties.map((p, i) => {
            const neverSynced = !p.lastSync;
            const stale = !neverSynced && isStale(p.lastSync, 24);
            return (
              <tr key={i} className="border-t border-gray-100">
                <td className="px-3 py-2">{p.name}</td>
                <td
                  className={`px-3 py-2 ${
                    stale ? "text-red-700" : "text-gray-700"
                  }`}
                  title={p.lastSync ? formatLocal(p.lastSync) : "never synced"}
                >
                  {neverSynced ? (
                    <span className="inline-block rounded bg-red-600 px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-white">
                      Never synced
                    </span>
                  ) : (
                    relativeTime(p.lastSync)
                  )}
                </td>
                <td className="px-3 py-2">
                  {p.liveDocId ? (
                    <a
                      href={`https://docs.google.com/document/d/${p.liveDocId}/edit`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-blue-600 underline"
                    >
                      open
                    </a>
                  ) : (
                    <span className="text-gray-400">—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
