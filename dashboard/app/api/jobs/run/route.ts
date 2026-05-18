import { NextResponse } from "next/server";
import { google } from "googleapis";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const PROJECT = "harbor-updatebot";
const LOCATION = "us-central1";

const ALLOWED_JOBS = ["slack-sync", "weekly-notify", "monthly-report"] as const;
type JobName = (typeof ALLOWED_JOBS)[number];

function isJobName(v: unknown): v is JobName {
  return typeof v === "string" && (ALLOWED_JOBS as readonly string[]).includes(v);
}

function executionIdFromName(name: string | null | undefined): string {
  if (!name) return "";
  const parts = name.split("/");
  return parts[parts.length - 1] || "";
}

export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json(
      { ok: false, error: "Invalid JSON body" },
      { status: 400 }
    );
  }

  if (!body || typeof body !== "object") {
    return NextResponse.json(
      { ok: false, error: "Body must be a JSON object" },
      { status: 400 }
    );
  }

  const { job, dryRun } = body as { job?: unknown; dryRun?: unknown };

  if (!isJobName(job)) {
    return NextResponse.json(
      {
        ok: false,
        error: `Invalid job. Allowed: ${ALLOWED_JOBS.join(", ")}`,
      },
      { status: 400 }
    );
  }

  const wantsDryRun = job === "monthly-report" && dryRun === true;

  try {
    const auth = new google.auth.GoogleAuth({
      scopes: ["https://www.googleapis.com/auth/cloud-platform"],
    });
    const run = google.run({ version: "v2", auth });

    const name = `projects/${PROJECT}/locations/${LOCATION}/jobs/${job}`;

    const requestBody: {
      overrides?: {
        containerOverrides?: { args: string[] }[];
      };
    } = {};

    if (wantsDryRun) {
      requestBody.overrides = {
        containerOverrides: [{ args: ["monthly-report", "--dry-run"] }],
      };
    }

    const res = await run.projects.locations.jobs.run({
      name,
      requestBody,
    });

    const op = res.data;
    // For Cloud Run v2 jobs.run, the operation metadata is the Execution
    // resource; metadata.name is the full execution resource path.
    const meta = (op.metadata ?? {}) as { name?: string };
    const executionName = meta.name || "";
    const executionId = executionIdFromName(executionName);
    const logsUrl = executionId
      ? `https://console.cloud.google.com/run/jobs/executions/details/${LOCATION}/${executionId}?project=${PROJECT}`
      : `https://console.cloud.google.com/run/jobs?project=${PROJECT}`;

    return NextResponse.json({
      ok: true,
      executionName,
      executionId,
      logsUrl,
    });
  } catch (e: unknown) {
    const err = e as { message?: string };
    return NextResponse.json(
      { ok: false, error: err.message || "Failed to trigger job" },
      { status: 500 }
    );
  }
}
