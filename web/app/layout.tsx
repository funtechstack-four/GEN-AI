import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Land Title Check",
  description: "Check a Kenyan land parcel against public records before you buy.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
