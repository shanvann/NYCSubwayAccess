import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NYC Subway Access Explorer",
  description: "Walking-distance subway accessibility across NYC neighborhoods",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="h-full m-0">{children}</body>
    </html>
  );
}
