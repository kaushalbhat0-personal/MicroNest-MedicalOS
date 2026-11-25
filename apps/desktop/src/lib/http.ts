import { invoke } from "@tauri-apps/api/core";

export type ApiResponse = { status: number; body: string };

export async function apiRequest(
  method: string,
  path: string,
  headers: Record<string, string> = {},
  body?: unknown,
): Promise<ApiResponse> {
  return invoke<ApiResponse>("api_request", {
    method,
    path,
    headers,
    body: body === undefined ? null : JSON.stringify(body),
  });
}

export function parseBody<T>(res: ApiResponse): T | null {
  if (!res.body) return null;
  try {
    return JSON.parse(res.body) as T;
  } catch {
    return null;
  }
}
