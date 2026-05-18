type Props = { status: string };

const STYLES: Record<string, string> = {
  success: "bg-green-100 text-green-800 border-green-300",
  partial: "bg-orange-100 text-orange-800 border-orange-300",
  failed: "bg-red-100 text-red-800 border-red-300",
  running: "bg-yellow-100 text-yellow-900 border-yellow-400",
};

export function StatusBadge({ status }: Props) {
  const cls = STYLES[status] || "bg-gray-100 text-gray-700 border-gray-300";
  return (
    <span
      className={`inline-block rounded border px-2 py-0.5 text-xs uppercase tracking-wide ${cls}`}
    >
      {status || "unknown"}
    </span>
  );
}
