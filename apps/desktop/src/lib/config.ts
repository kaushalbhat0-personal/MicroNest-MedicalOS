import { invoke } from "@tauri-apps/api/core";

export async function getApiBaseUrl(): Promise<string> {
  const fromEnv = import.meta.env.VITE_HOS_API_BASE_URL as string | undefined;
  if (fromEnv && fromEnv.length > 0) return fromEnv.replace(/\/$/, "");
  try {
    const fromRust = await invoke<string>("get_api_base_url");
    return fromRust.replace(/\/$/, "");
  } catch {
    return "http://127.0.0.1:8000";
  }
}

export async function getChannel(): Promise<string> {
  const fromEnv = import.meta.env.VITE_HOS_CHANNEL as string | undefined;
  if (fromEnv) return fromEnv;
  try {
    return await invoke<string>("get_channel");
  } catch {
    return "development";
  }
}

export async function getClientInstanceId(): Promise<string> {
  try {
    return await invoke<string>("get_client_instance_id");
  } catch {
    const key = "hos_desktop_instance_id";
    let id = sessionStorage.getItem(key);
    if (!id) {
      id = crypto.randomUUID();
      sessionStorage.setItem(key, id);
    }
    return id;
  }
}
