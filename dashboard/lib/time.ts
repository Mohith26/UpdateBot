// Pure helpers for time formatting. Used on both server and client.

export function parseTs(s: string): Date | null {
  if (!s) return null;
  const t = Date.parse(s);
  if (Number.isNaN(t)) return null;
  return new Date(t);
}

export function relativeTime(input: string | Date | null, now = new Date()): string {
  const d = typeof input === "string" ? parseTs(input) : input;
  if (!d) return "—";
  const diffMs = now.getTime() - d.getTime();
  const sec = Math.round(diffMs / 1000);
  const abs = Math.abs(sec);
  const sign = sec >= 0 ? "" : "in ";
  const suffix = sec >= 0 ? " ago" : "";
  let value: string;
  if (abs < 60) value = `${abs}s`;
  else if (abs < 3600) value = `${Math.round(abs / 60)}m`;
  else if (abs < 86400) value = `${Math.round(abs / 3600)}h`;
  else if (abs < 86400 * 30) value = `${Math.round(abs / 86400)}d`;
  else if (abs < 86400 * 365) value = `${Math.round(abs / (86400 * 30))}mo`;
  else value = `${Math.round(abs / (86400 * 365))}y`;
  return `${sign}${value}${suffix}`;
}

export function formatDuration(seconds: number): string {
  if (!seconds || seconds < 0) return "—";
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m < 60) return s ? `${m}m ${s}s` : `${m}m`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return rm ? `${h}h ${rm}m` : `${h}h`;
}

export function isStale(input: string, hours = 24, now = new Date()): boolean {
  const d = parseTs(input);
  if (!d) return true;
  return now.getTime() - d.getTime() > hours * 3600 * 1000;
}

export function formatLocal(input: string | Date | null): string {
  const d = typeof input === "string" ? parseTs(input) : input;
  if (!d) return "—";
  try {
    const fmt = new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
      timeZoneName: "short",
    });
    return fmt.format(d);
  } catch {
    return d.toLocaleString();
  }
}
