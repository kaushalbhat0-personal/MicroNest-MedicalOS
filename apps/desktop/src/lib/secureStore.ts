import { invoke } from "@tauri-apps/api/core";

/**
 * SecureTokenStore bridge. Refresh tokens go through Rust DPAPI commands.
 * Never use localStorage/sessionStorage for refresh tokens.
 */
export const SecureTokenStore = {
  async storeRefreshToken(token: string): Promise<void> {
    await invoke("store_refresh_token", { token });
  },
  async retrieveRefreshToken(): Promise<string | null> {
    try {
      return await invoke<string>("retrieve_refresh_token");
    } catch (e) {
      const msg = String(e);
      if (msg.includes("no refresh token") || msg.includes("Missing")) return null;
      throw e;
    }
  },
  async deleteRefreshToken(): Promise<void> {
    await invoke("delete_refresh_token");
  },
  async clearSession(): Promise<void> {
    await invoke("clear_session");
  },
};
