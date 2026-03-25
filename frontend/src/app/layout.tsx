import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ozon Ads Control Room",
  description: "Next.js migration UI for the Ozon Ads platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
