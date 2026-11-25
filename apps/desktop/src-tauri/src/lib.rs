mod api_http;
mod secure_store;

use std::collections::HashMap;

use secure_store::StoreError;

fn map_store_err(e: StoreError) -> String {
    e.to_string()
}

#[tauri::command]
fn store_refresh_token(token: String) -> Result<(), String> {
    secure_store::store_refresh_token(&token).map_err(map_store_err)
}

#[tauri::command]
fn retrieve_refresh_token() -> Result<String, String> {
    secure_store::retrieve_refresh_token().map_err(map_store_err)
}

#[tauri::command]
fn delete_refresh_token() -> Result<(), String> {
    secure_store::delete_refresh_token().map_err(map_store_err)
}

#[tauri::command]
fn clear_session() -> Result<(), String> {
    secure_store::clear_session().map_err(map_store_err)
}

#[tauri::command]
fn get_api_base_url() -> String {
    api_http::get_api_base_url()
}

#[tauri::command]
fn get_client_instance_id() -> Result<String, String> {
    use std::fs;
    let dir = secure_store::credentials_dir().map_err(map_store_err)?;
    let path = dir.join("client_instance_id.txt");
    if path.exists() {
        return fs::read_to_string(&path).map_err(|e| e.to_string());
    }
    let id = uuid_v4_simple();
    fs::write(&path, &id).map_err(|e| e.to_string())?;
    Ok(id)
}

#[tauri::command]
fn get_channel() -> String {
    std::env::var("HOS_CHANNEL")
        .unwrap_or_else(|_| "development".to_string())
}

#[derive(serde::Serialize)]
struct AutologinDto {
    email: String,
    password: String,
}

/// Synthetic-only autologin for local evidence runs. Empty if unset.
#[tauri::command]
fn get_m3_autologin() -> Option<AutologinDto> {
    let email = std::env::var("HOS_M3_AUTOLOGIN_EMAIL").ok()?;
    let password = std::env::var("HOS_M3_AUTOLOGIN_PASSWORD").ok()?;
    if email.is_empty() || password.is_empty() {
        return None;
    }
    Some(AutologinDto { email, password })
}

#[tauri::command]
fn write_runtime_evidence(json: String) -> Result<String, String> {
    // Scrub accidental token-looking fields before write.
    if json.contains("access_token") || json.contains("refresh_token") {
        return Err("evidence must not contain tokens".into());
    }
    let dir = secure_store::credentials_dir()
        .map_err(map_store_err)?
        .parent()
        .map(|p| p.join("evidence"))
        .ok_or_else(|| "evidence path".to_string())?;
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let path = dir.join("m3_runtime_evidence.json");
    std::fs::write(&path, json).map_err(|e| e.to_string())?;
    Ok(path.to_string_lossy().to_string())
}

#[tauri::command]
fn evidence_refresh_file_state() -> Result<serde_json::Value, String> {
    let path = secure_store::credentials_dir()
        .map_err(map_store_err)?
        .join("refresh.dpapi");
    if !path.exists() {
        return Ok(serde_json::json!({ "exists": false }));
    }
    let bytes = std::fs::read(&path).map_err(|e| e.to_string())?;
    let as_txt = String::from_utf8_lossy(&bytes);
    Ok(serde_json::json!({
        "exists": true,
        "bytes": bytes.len(),
        "looks_like_json_envelope": as_txt.contains("ciphertext_b64"),
        "contains_dot_token_shape": as_txt.contains(".secret") || as_txt.contains("refresh_token"),
    }))
}

#[derive(serde::Serialize)]
struct ApiResponseDto {
    status: u16,
    body: String,
}

/// Allowlisted HTTP to the configured API base only (no CORS dependency).
#[tauri::command]
fn api_request(
    method: String,
    path: String,
    headers: HashMap<String, String>,
    body: Option<String>,
) -> Result<ApiResponseDto, String> {
    let resp = api_http::request(&method, &path, headers, body).map_err(|e| e.to_string())?;
    Ok(ApiResponseDto {
        status: resp.status,
        body: resp.body,
    })
}

fn uuid_v4_simple() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    format!("{:032x}", nanos ^ 0xA5A5_DEAD_BEEF_u128)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            store_refresh_token,
            retrieve_refresh_token,
            delete_refresh_token,
            clear_session,
            get_api_base_url,
            get_client_instance_id,
            get_channel,
            api_request,
            get_m3_autologin,
            write_runtime_evidence,
            evidence_refresh_file_state,
        ])
        .run(tauri::generate_context!())
        .expect("error while running Healthcare OS desktop");
}
