"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

type JobName = "slack-sync" | "weekly-notify" | "monthly-report";

type TriggerKey =
  | "slack-sync"
  | "weekly-notify"
  | "monthly-report-dry"
  | "monthly-report";

type SuccessState = {
  kind: "success";
  executionId: string;
  logsUrl: string;
};
type ErrorState = { kind: "error"; message: string };
type AuthExpiredState = { kind: "auth-expired" };
type StatusState = SuccessState | ErrorState | AuthExpiredState | null;

const DASHBOARD_URL =
  "https://updatebot-dashboard-818467834208.us-central1.run.app/";

type TriggerDef = {
  key: TriggerKey;
  label: string;
  job: JobName;
  dryRun: boolean;
  confirm: string;
  destructive?: boolean;
  // When set, replaces window.confirm() with a window.prompt() that
  // requires the operator to type the exact phrase to proceed. Stronger
  // than a one-click confirm — prevents misclicks from shipping decks.
  requireTypedConfirmation?: string;
};

// Post-trigger refresh schedule (seconds after kickoff). Jobs can take
// ~2 minutes, so a single refresh at +5s leaves the dashboard stale for
// the rest of the run. This polls until the run row likely terminalizes.
const REFRESH_OFFSETS_MS = [5_000, 15_000, 30_000, 60_000, 120_000, 240_000];

const TRIGGERS: TriggerDef[] = [
  {
    key: "slack-sync",
    label: "Run slack-sync",
    job: "slack-sync",
    dryRun: false,
    confirm:
      "Trigger slack-sync now? This will read Slack and may write to the live doc.",
  },
  {
    key: "weekly-notify",
    label: "Run weekly-notify",
    job: "weekly-notify",
    dryRun: false,
    confirm:
      "Trigger weekly-notify now? This will post doc review links to the Slack review channel.",
  },
  {
    key: "monthly-report-dry",
    label: "Run monthly-report (dry-run)",
    job: "monthly-report",
    dryRun: true,
    confirm:
      "Trigger monthly-report in dry-run mode? Resolves placeholders only — no Slides, Drive, or Slack writes.",
  },
  {
    key: "monthly-report",
    label: "Run monthly-report",
    job: "monthly-report",
    dryRun: false,
    confirm:
      "⚠ This will create real investor decks and post to the review Slack channel.\n\nType the word MONTHLY (in caps) to confirm:",
    destructive: true,
    requireTypedConfirmation: "MONTHLY",
  },
];

export function JobTriggers() {
  const router = useRouter();
  const [running, setRunning] = useState<Set<TriggerKey>>(new Set());
  const [statuses, setStatuses] = useState<Record<TriggerKey, StatusState>>({
    "slack-sync": null,
    "weekly-notify": null,
    "monthly-report-dry": null,
    "monthly-report": null,
  });
  const timers = useRef<Partial<Record<TriggerKey, ReturnType<typeof setTimeout>>>>({});
  const refreshTimers = useRef<Partial<Record<TriggerKey, ReturnType<typeof setTimeout>[]>>>({});

  useEffect(() => {
    const t = timers.current;
    const r = refreshTimers.current;
    return () => {
      Object.values(t).forEach((id) => id && clearTimeout(id));
      Object.values(r).forEach((ids) => ids?.forEach((id) => clearTimeout(id)));
    };
  }, []);

  function schedulePollRefresh(key: TriggerKey) {
    const existing = refreshTimers.current[key];
    if (existing) existing.forEach((id) => clearTimeout(id));
    refreshTimers.current[key] = REFRESH_OFFSETS_MS.map((ms) =>
      setTimeout(() => router.refresh(), ms),
    );
  }

  function setStatus(key: TriggerKey, status: StatusState) {
    setStatuses((s) => ({ ...s, [key]: status }));
    const existing = timers.current[key];
    if (existing) clearTimeout(existing);
    if (status) {
      timers.current[key] = setTimeout(() => {
        setStatuses((s) => ({ ...s, [key]: null }));
      }, 30_000);
    }
  }

  async function trigger(def: TriggerDef) {
    if (running.has(def.key)) return;
    if (def.requireTypedConfirmation) {
      const typed = window.prompt(def.confirm);
      if (typed !== def.requireTypedConfirmation) {
        if (typed !== null) {
          setStatus(def.key, {
            kind: "error",
            message: `Confirmation phrase did not match "${def.requireTypedConfirmation}"; aborted.`,
          });
        }
        return;
      }
    } else if (!confirm(def.confirm)) {
      return;
    }

    setRunning((cur) => {
      const next = new Set(cur);
      next.add(def.key);
      return next;
    });
    setStatus(def.key, null);

    try {
      const res = await fetch("/api/jobs/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job: def.job, dryRun: def.dryRun }),
        // Surface IAP's 302→OAuth bounce as an opaqueredirect we can detect.
        redirect: "manual",
        credentials: "same-origin",
      });
      if (
        res.status === 401 ||
        res.status === 403 ||
        res.type === "opaqueredirect" ||
        res.redirected
      ) {
        // IAP rejected the request or bounced us to the OAuth login flow.
        setStatus(def.key, { kind: "auth-expired" });
        return;
      }
      const data = (await res.json().catch(() => ({}))) as {
        ok?: boolean;
        executionId?: string;
        logsUrl?: string;
        error?: string;
      };
      if (!res.ok || !data.ok) {
        setStatus(def.key, {
          kind: "error",
          message: data.error || `HTTP ${res.status}`,
        });
      } else {
        setStatus(def.key, {
          kind: "success",
          executionId: data.executionId || "(unknown)",
          logsUrl: data.logsUrl || "#",
        });
        schedulePollRefresh(def.key);
      }
    } catch (e: unknown) {
      const err = e as { message?: string };
      setStatus(def.key, {
        kind: "error",
        message: err.message || "Network error",
      });
    } finally {
      setRunning((cur) => {
        if (!cur.has(def.key)) return cur;
        const next = new Set(cur);
        next.delete(def.key);
        return next;
      });
    }
  }

  return (
    <section className="mb-10">
      <h2 className="mb-3 text-xs uppercase tracking-wider text-gray-500">
        Trigger a job run
      </h2>
      <div className="rounded border border-gray-200 bg-white p-4">
        <div className="flex flex-wrap gap-2">
          {TRIGGERS.map((t) => {
            const isRunning = running.has(t.key);
            const base =
              "rounded border px-3 py-1.5 text-xs disabled:opacity-50 disabled:cursor-not-allowed";
            const styles = t.destructive
              ? "border-red-300 bg-red-50 text-red-700 hover:bg-red-100"
              : "border-gray-300 bg-white text-gray-800 hover:bg-gray-50";
            return (
              <button
                key={t.key}
                onClick={() => trigger(t)}
                disabled={isRunning}
                className={`${base} ${styles}`}
              >
                {isRunning ? "Running…" : t.label}
              </button>
            );
          })}
        </div>

        <div className="mt-3 space-y-2">
          {TRIGGERS.map((t) => {
            const s = statuses[t.key];
            if (!s) return null;
            if (s.kind === "success") {
              return (
                <div key={t.key} className="text-xs text-gray-700">
                  <span className="font-medium">{t.label}:</span> Started —
                  execution <code className="text-gray-900">{s.executionId}</code>.{" "}
                  <a
                    href={s.logsUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="text-blue-600 underline"
                  >
                    View logs ↗
                  </a>
                </div>
              );
            }
            if (s.kind === "auth-expired") {
              return (
                <div
                  key={t.key}
                  className="rounded border-2 border-red-400 bg-yellow-50 p-3 text-sm text-red-800"
                >
                  <div className="font-semibold">
                    {t.label}: Session expired
                  </div>
                  <div className="mt-1">
                    Open a new tab to{" "}
                    <a
                      href={DASHBOARD_URL}
                      target="_blank"
                      rel="noreferrer"
                      className="font-medium text-blue-700 underline"
                    >
                      {DASHBOARD_URL}
                    </a>{" "}
                    and sign in again. Then return here.
                  </div>
                </div>
              );
            }
            return (
              <div key={t.key} className="text-xs text-red-700">
                <span className="font-medium">{t.label}:</span> Failed —{" "}
                {s.message}
              </div>
            );
          })}
        </div>

        <p className="mt-3 text-xs text-gray-400">
          Once the job finishes, it appears in Recent runs below.
        </p>
      </div>
    </section>
  );
}
