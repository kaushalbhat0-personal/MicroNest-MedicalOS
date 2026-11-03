import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "Healthcare OS" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a href="#main-content" className="skip-link">
          Skip to content
        </a>
        <main id="main-content" className="container" tabIndex={-1}>
          {children}
        </main>
      </body>
    </html>
  );
}
