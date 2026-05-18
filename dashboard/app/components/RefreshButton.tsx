"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

export function RefreshButton() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  return (
    <button
      onClick={() =>
        startTransition(() => {
          router.refresh();
        })
      }
      className="rounded border border-gray-300 bg-white px-3 py-1 text-xs hover:bg-gray-50 disabled:opacity-50"
      disabled={pending}
    >
      {pending ? "Refreshing..." : "Refresh"}
    </button>
  );
}
