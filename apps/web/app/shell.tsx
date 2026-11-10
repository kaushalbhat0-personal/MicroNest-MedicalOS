"use client";

import { usePathname } from "next/navigation";
import { AppShell } from "@healthcare-os/ui";
import { NAV } from "@/lib/nav";

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <AppShell nav={NAV} currentPath={pathname}>
      {children}
    </AppShell>
  );
}
