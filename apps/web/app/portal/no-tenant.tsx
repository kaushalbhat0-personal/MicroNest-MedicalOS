"use client";

import Link from "next/link";
import { Card } from "@healthcare-os/ui";

export function NoTenantHint() {
  return (
    <Card title="Choose your care organization">
      <p className="hos-helper">
        Start at the <Link href="/portal">portal home page</Link> to pick where to continue.
      </p>
    </Card>
  );
}
