import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Loan File Assistant",
  description:
    "Extracts terms from bridge loan documents, flags underwriting issues, and answers questions with citations. Demo on fictional data.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
