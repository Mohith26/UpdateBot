import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";

export const metadata: Metadata = {
  title: "UpdateBot",
  description: "UpdateBot admin dashboard",
};

function parseIapEmail(raw: string | null | undefined): string | null {
  if (!raw) return null;
  // IAP format: "accounts.google.com:user@harborcap.com"
  const idx = raw.indexOf(":");
  const email = idx >= 0 ? raw.slice(idx + 1) : raw;
  // Defensive: must look like an email.
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return null;
  return email;
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const hdrs = headers();
  const email = parseIapEmail(hdrs.get("x-goog-authenticated-user-email"));

  return (
    <html lang="en">
      <body className="font-mono text-sm antialiased">
        {email && (
          <div className="mx-auto flex max-w-6xl justify-end px-6 pt-4 text-sm text-gray-500">
            Signed in as {email}
          </div>
        )}
        {children}
      </body>
    </html>
  );
}
