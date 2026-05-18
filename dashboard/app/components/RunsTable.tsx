"use client";

import { Fragment, useState } from "react";
import type { Run, RunDetail } from "@/lib/sheets";
import { formatDuration, formatLocal, parseTs, relativeTime } from "@/lib/time";
import { StatusBadge } from "./StatusBadge";

// Hardcoded to match deploy.sh — when those change, update here too.
const GCP_PROJECT_ID = "harbor-updatebot";
const GCP_REGION = "us-central1";
const CONFIG_SHEET_ID = "1rzWizfU17kk-Ytk1nu1rfOBSuLI7JKlryYUAj8wU49A";

// Typical end-to-end durations in seconds for each job. A "running" row
// older than 2× this is almost certainly a crashed execution that never
// finalized — surface it in red so the operator triages.
const TYPICAL_DURATION_SECONDS: Record<string, number> = {
  "slack-sync": 60,
  "weekly-notify": 60,
  "monthly-report": 120,
  "monthly-report (dry-run)": 30,
};
const DEFAULT_TYPICAL_DURATION_SECONDS = 120;

function jobBaseName(jobName: string): string {
  // Drop the " (dry-run)" suffix to find the Cloud Run job name.
  return jobName.replace(/\s*\(dry-run\)\s*$/, "");
}

function isLikelyCrashed(run: Run, now = new Date()): boolean {
  if (run.status !== "running") return false;
  const started = parseTs(run.timestamp);
  if (!started) return false;
  const typical =
    TYPICAL_DURATION_SECONDS[run.jobName] ?? DEFAULT_TYPICAL_DURATION_SECONDS;
  const ageSec = (now.getTime() - started.getTime()) / 1000;
  return ageSec > 2 * typical;
}

function cloudRunExecutionsUrl(jobName: string): string {
  const job = encodeURIComponent(jobBaseName(jobName));
  return `https://console.cloud.google.com/run/jobs/details/${GCP_REGION}/${job}/executions?project=${GCP_PROJECT_ID}`;
}

function cloudRunLogsUrl(jobName: string): string {
  const job = jobBaseName(jobName);
  const query = `resource.type="cloud_run_job"\nresource.labels.job_name="${job}"`;
  return `https://console.cloud.google.com/logs/query;query=${encodeURIComponent(
    query,
  )}?project=${GCP_PROJECT_ID}`;
}

function configSheetUrl(): string {
  return `https://docs.google.com/spreadsheets/d/${CONFIG_SHEET_ID}/edit`;
}

function isDryRun(run: Run): boolean {
  return (
    /\bdry-run\b/i.test(run.jobName) ||
    /^dry-run:/i.test(run.summary || "")
  );
}

function PlaceholdersTable({ values }: { values: Record<string, unknown> }) {
  const entries = Object.entries(values);
  if (entries.length === 0) return null;
  return (
    <div className="mt-2 overflow-x-auto rounded border border-gray-200 bg-white">
      <table className="w-full text-left text-xs">
        <tbody>
          {entries.map(([k, v]) => (
            <tr key={k} className="border-t border-gray-100 first:border-t-0">
              <td className="w-48 px-2 py-1 align-top font-mono text-gray-500">
                {`{{${k}}}`}
              </td>
              <td className="px-2 py-1 align-top whitespace-pre-wrap text-gray-800">
                {String(v ?? "")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DetailItem({ d }: { d: RunDetail }) {
  const urls = (d.urls ?? {}) as Record<string, string>;
  const placeholders = (d as { placeholders?: Record<string, unknown> })
    .placeholders;
  return (
    <li className="border-l-2 border-gray-200 pl-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{d.name || "(unnamed)"}</span>
        {d.status ? <StatusBadge status={String(d.status)} /> : null}
        {urls.doc ? (
          <a
            href={urls.doc}
            target="_blank"
            rel="noreferrer"
            className="text-blue-600 underline"
          >
            doc
          </a>
        ) : null}
        {urls.deck ? (
          <a
            href={urls.deck}
            target="_blank"
            rel="noreferrer"
            className="text-blue-600 underline"
          >
            deck
          </a>
        ) : null}
      </div>
      {d.error ? (
        <div className="mt-1 text-xs text-red-700 whitespace-pre-wrap">
          {String(d.error)}
        </div>
      ) : null}
      {placeholders && typeof placeholders === "object" ? (
        <PlaceholdersTable values={placeholders as Record<string, unknown>} />
      ) : null}
    </li>
  );
}

export function RunsTable({ runs }: { runs: Run[] }) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  if (runs.length === 0) {
    return (
      <div className="rounded border border-dashed border-gray-300 bg-white p-6 text-gray-500">
        No runs recorded yet. Trigger a job above to populate, or check that
        the RunLog tab exists on the config sheet.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded border border-gray-200 bg-white">
      <table className="w-full text-left">
        <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
          <tr>
            <th className="px-3 py-2 font-normal">When</th>
            <th className="px-3 py-2 font-normal">Job</th>
            <th className="px-3 py-2 font-normal">Status</th>
            <th className="px-3 py-2 font-normal">Properties</th>
            <th className="px-3 py-2 font-normal">Duration</th>
            <th className="px-3 py-2 font-normal">Summary</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => {
            const isOpen = openIndex === r.index;
            const crashed = isLikelyCrashed(r);
            const dryRun = isDryRun(r);
            return (
              <Fragment key={r.index}>
                <tr
                  onClick={() => setOpenIndex(isOpen ? null : r.index)}
                  className={`cursor-pointer border-t border-gray-100 hover:bg-gray-50 ${
                    crashed
                      ? "bg-red-50 hover:bg-red-100"
                      : isOpen
                        ? "bg-gray-50"
                        : ""
                  }`}
                >
                  <td className="px-3 py-2" title={formatLocal(r.timestamp)}>
                    <div className="text-gray-900">{relativeTime(r.timestamp)}</div>
                    <div className="text-xs text-gray-500">
                      {formatLocal(r.timestamp)}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span>{r.jobName || "—"}</span>
                      {dryRun ? (
                        <span className="inline-block rounded border border-blue-300 bg-blue-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-blue-700">
                          dry-run
                        </span>
                      ) : null}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge status={r.status} />
                      {crashed ? (
                        <span className="inline-block rounded border border-red-400 bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-800">
                          likely crashed
                        </span>
                      ) : null}
                    </div>
                  </td>
                  <td className="px-3 py-2 tabular-nums">
                    <span className="text-green-700">{r.processed}</span>
                    <span className="text-gray-400">/</span>
                    <span
                      className={r.failed > 0 ? "text-red-700" : "text-gray-400"}
                    >
                      {r.failed}
                    </span>
                  </td>
                  <td className="px-3 py-2 tabular-nums">
                    {formatDuration(r.durationSeconds)}
                  </td>
                  <td className="px-3 py-2 text-gray-600">{r.summary || "—"}</td>
                </tr>
                {isOpen ? (
                  <tr className="bg-gray-50">
                    <td colSpan={6} className="px-6 py-4">
                      <div className="mb-3 flex flex-wrap items-center gap-3 text-xs">
                        <span className="uppercase tracking-wide text-gray-500">
                          Details ({formatLocal(r.timestamp)})
                        </span>
                        {r.jobName ? (
                          <>
                            <a
                              href={cloudRunExecutionsUrl(r.jobName)}
                              target="_blank"
                              rel="noreferrer"
                              className="text-blue-600 underline"
                            >
                              Cloud Run executions ↗
                            </a>
                            <a
                              href={cloudRunLogsUrl(r.jobName)}
                              target="_blank"
                              rel="noreferrer"
                              className="text-blue-600 underline"
                            >
                              Logs ↗
                            </a>
                          </>
                        ) : null}
                        <a
                          href={configSheetUrl()}
                          target="_blank"
                          rel="noreferrer"
                          className="text-blue-600 underline"
                        >
                          Config sheet ↗
                        </a>
                      </div>
                      {crashed ? (
                        <div className="mb-3 rounded border border-red-300 bg-red-50 p-2 text-xs text-red-800">
                          This run was marked <code>running</code> but has been
                          open for longer than 2× the typical duration for{" "}
                          <code>{jobBaseName(r.jobName)}</code>. The execution
                          probably crashed before <code>finalize_run</code>{" "}
                          could write a terminal status. Use the Cloud Run logs
                          link above to confirm and trigger a new run.
                        </div>
                      ) : null}
                      {r.details && r.details.length > 0 ? (
                        <ul className="space-y-2">
                          {r.details.map((d, i) => (
                            <DetailItem key={i} d={d} />
                          ))}
                        </ul>
                      ) : r.detailsRaw ? (
                        <pre className="overflow-x-auto rounded border border-gray-200 bg-white p-3 text-xs text-gray-700">
                          {r.detailsRaw}
                        </pre>
                      ) : (
                        <div className="text-gray-500">No details recorded.</div>
                      )}
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
