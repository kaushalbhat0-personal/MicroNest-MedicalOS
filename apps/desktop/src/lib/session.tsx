import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";
import {
  fetchWorkspaceContext,
  PublicSession,
  TenantOption,
  WorkspaceContext,
} from "./api";

type SessionState = {
  profile: PublicSession | null;
  tenant: TenantOption | null;
  workspace: WorkspaceContext | null;
  setProfile: (p: PublicSession | null) => void;
  selectTenant: (t: TenantOption) => Promise<void>;
  clearTenantScoped: () => void;
  reset: () => void;
};

const Ctx = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<PublicSession | null>(null);
  const [tenant, setTenant] = useState<TenantOption | null>(null);
  const [workspace, setWorkspace] = useState<WorkspaceContext | null>(null);

  const clearTenantScoped = useCallback(() => {
    setWorkspace(null);
  }, []);

  const selectTenant = useCallback(async (t: TenantOption) => {
    clearTenantScoped();
    setTenant(t);
    const ctx = await fetchWorkspaceContext(t.id);
    setWorkspace(ctx);
  }, [clearTenantScoped]);

  const reset = useCallback(() => {
    setProfile(null);
    setTenant(null);
    setWorkspace(null);
  }, []);

  const value = useMemo(
    () => ({
      profile,
      tenant,
      workspace,
      setProfile,
      selectTenant,
      clearTenantScoped,
      reset,
    }),
    [profile, tenant, workspace, selectTenant, clearTenantScoped, reset],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): SessionState {
  const v = useContext(Ctx);
  if (!v) throw new Error("SessionProvider required");
  return v;
}
