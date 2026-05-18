import { google } from "googleapis";

const SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"];

function getSheetId(): string {
  return (
    process.env.CONFIG_SHEET_ID ||
    "1rzWizfU17kk-Ytk1nu1rfOBSuLI7JKlryYUAj8wU49A"
  );
}

function getAuth() {
  // ADC: On Cloud Run, picks up the attached service account.
  // Locally, picks up ~/.config/gcloud/application_default_credentials.json
  // after `gcloud auth application-default login`.
  return new google.auth.GoogleAuth({ scopes: SCOPES });
}

function getSheets() {
  const auth = getAuth();
  return google.sheets({ version: "v4", auth });
}

export type RunDetail = {
  name?: string;
  status?: string;
  error?: string;
  urls?: { deck?: string; doc?: string } | Record<string, string>;
  [k: string]: unknown;
};

export type Run = {
  index: number; // 0 = newest
  timestamp: string;
  jobName: string;
  status: string;
  processed: number;
  failed: number;
  durationSeconds: number;
  summary: string;
  details: RunDetail[] | null;
  detailsRaw: string;
};

export type Property = {
  name: string;
  liveDocId: string;
  lastSync: string;
};

export type Result<T> = { ok: true; data: T } | { ok: false; error: string };

function toInt(v: unknown): number {
  const n = parseInt(String(v ?? "").trim(), 10);
  return Number.isFinite(n) ? n : 0;
}

export async function fetchRuns(limit = 25): Promise<Result<Run[]>> {
  try {
    const sheets = getSheets();
    const res = await sheets.spreadsheets.values.get({
      spreadsheetId: getSheetId(),
      range: "RunLog!A2:H1000",
    });
    const rows = res.data.values ?? [];
    // Newest at the bottom → reverse.
    const reversed = [...rows].reverse();
    const runs: Run[] = reversed.slice(0, limit).map((row, i) => {
      const detailsRaw = String(row[7] ?? "");
      let details: RunDetail[] | null = null;
      if (detailsRaw.trim()) {
        try {
          const parsed = JSON.parse(detailsRaw);
          if (Array.isArray(parsed)) {
            details = parsed as RunDetail[];
          }
        } catch {
          details = null;
        }
      }
      return {
        index: i,
        timestamp: String(row[0] ?? ""),
        jobName: String(row[1] ?? ""),
        status: String(row[2] ?? "").toLowerCase(),
        processed: toInt(row[3]),
        failed: toInt(row[4]),
        durationSeconds: toInt(row[5]),
        summary: String(row[6] ?? ""),
        details,
        detailsRaw,
      };
    });
    return { ok: true, data: runs };
  } catch (e: unknown) {
    const err = e as { code?: number; message?: string };
    if (err.code === 400 && /Unable to parse range/i.test(err.message ?? "")) {
      // RunLog tab doesn't exist — surface as an actionable error so the
      // operator can distinguish "tab missing" from "tab present but empty".
      return {
        ok: false,
        error:
          "RunLog tab not found on the config sheet — create a tab named 'RunLog' with headers in row 1: timestamp_utc, job_name, status, properties_processed, properties_failed, duration_seconds, summary, details_json",
      };
    }
    return {
      ok: false,
      error: err.message || "Unknown error reading RunLog",
    };
  }
}

export async function fetchProperties(): Promise<Result<Property[]>> {
  try {
    const sheets = getSheets();
    // The main config tab has no name prefix per HANDOFF.md.
    const res = await sheets.spreadsheets.values.get({
      spreadsheetId: getSheetId(),
      range: "A1:N200",
    });
    const rows = res.data.values ?? [];
    // Skip the header row (row 0). The bot uses rows starting at row 2.
    const dataRows = rows.slice(1).filter((r) => (r?.[0] ?? "").toString().trim());
    const properties: Property[] = dataRows.map((row) => ({
      name: String(row[0] ?? ""),
      liveDocId: String(row[2] ?? ""),
      lastSync: String(row[13] ?? ""),
    }));
    return { ok: true, data: properties };
  } catch (e: unknown) {
    const err = e as { message?: string };
    return {
      ok: false,
      error: err.message || "Unknown error reading config sheet",
    };
  }
}
