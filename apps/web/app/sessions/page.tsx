"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  LoadingState,
  Table,
  Td,
  Th,
} from "@healthcare-os/ui";
import { api } from "@/lib/api";
import { Shell } from "../shell";

type SessionInfo = { id: string; created_at: string; ip: string | null; current: boolean };

export default function SessionsPage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  function load() {
    setLoading(true);
    api
      .get<SessionInfo[]>("/api/v1/auth/sessions")
      .then((s) => {
        setSessions(s);
        setLoading(false);
      })
      .catch(() => router.push("/login"));
  }

  useEffect(load, [router]);

  async function revoke(id: string) {
    try {
      await api.del(`/api/v1/auth/sessions/${id}`);
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <Shell>
      <Card title="Sessions">
        {error ? (
          <Alert tone="danger" title="Something went wrong">
            {error}
          </Alert>
        ) : null}
        {loading ? (
          <LoadingState label="Loading sessions" />
        ) : sessions.length === 0 ? (
          <EmptyState title="No sessions">Sign in on a device to see it here.</EmptyState>
        ) : (
          <Table
            caption="Active sessions"
            columns={
              <>
                <Th>Started</Th>
                <Th>IP</Th>
                <Th>
                  <span style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}>
                    Actions
                  </span>
                </Th>
              </>
            }
          >
            {sessions.map((s) => (
              <tr key={s.id}>
                <Td>
                  {new Date(s.created_at).toLocaleString()}
                  {s.current ? (
                    <>
                      {" "}
                      <Badge tone="info">this device</Badge>
                    </>
                  ) : null}
                </Td>
                <Td>{s.ip ?? "-"}</Td>
                <Td>
                  {!s.current && (
                    <Button size="sm" variant="secondary" onClick={() => void revoke(s.id)}>
                      Revoke
                    </Button>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </Shell>
  );
}
