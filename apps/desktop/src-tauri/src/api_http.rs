//! Host-allowlisted HTTP client for the Healthcare OS API.
//! Desktop never depends on browser CORS for authenticated calls.

use std::collections::HashMap;
use std::sync::OnceLock;

use serde::{Deserialize, Serialize};
use url::Url;

#[derive(Debug, Serialize, Deserialize)]
pub struct ApiResponse {
    pub status: u16,
    pub body: String,
}

#[derive(Debug, thiserror::Error)]
pub enum ApiError {
    #[error("invalid API base URL")]
    BadBase,
    #[error("request URL host is not allowlisted")]
    HostDenied,
    #[error("network error")]
    Network,
    #[error("invalid request")]
    BadRequest,
}

fn api_base() -> String {
    std::env::var("HOS_API_BASE_URL")
        .ok()
        .filter(|s| !s.is_empty())
        .or_else(|| option_env!("HOS_API_BASE_URL").map(|s| s.to_string()))
        .unwrap_or_else(|| "http://127.0.0.1:8000".to_string())
        .trim_end_matches('/')
        .to_string()
}

fn allowed_origin_host() -> Result<(String, u16, String), ApiError> {
    let base = api_base();
    let parsed = Url::parse(&base).map_err(|_| ApiError::BadBase)?;
    let host = parsed.host_str().ok_or(ApiError::BadBase)?.to_string();
    let port = parsed.port_or_known_default().unwrap_or(80);
    let scheme = parsed.scheme().to_string();
    if scheme != "http" && scheme != "https" {
        return Err(ApiError::BadBase);
    }
    Ok((host, port, scheme))
}

fn assert_url_allowed(target: &str) -> Result<Url, ApiError> {
    let url = Url::parse(target).map_err(|_| ApiError::BadRequest)?;
    let (ahost, aport, ascheme) = allowed_origin_host()?;
    let host = url.host_str().ok_or(ApiError::HostDenied)?;
    let port = url.port_or_known_default().unwrap_or(80);
    if url.scheme() != ascheme || host != ahost || port != aport {
        return Err(ApiError::HostDenied);
    }
    Ok(url)
}

fn client() -> &'static reqwest::blocking::Client {
    static CLIENT: OnceLock<reqwest::blocking::Client> = OnceLock::new();
    CLIENT.get_or_init(|| {
        reqwest::blocking::Client::builder()
            .timeout(std::time::Duration::from_secs(30))
            .build()
            .expect("http client")
    })
}

pub fn get_api_base_url() -> String {
    api_base()
}

pub fn request(
    method: &str,
    path_or_url: &str,
    headers: HashMap<String, String>,
    body: Option<String>,
) -> Result<ApiResponse, ApiError> {
    let url = if path_or_url.starts_with("http://") || path_or_url.starts_with("https://") {
        path_or_url.to_string()
    } else {
        format!("{}{}", api_base(), path_or_url)
    };
    let url = assert_url_allowed(&url)?;
    let method = method
        .parse::<reqwest::Method>()
        .map_err(|_| ApiError::BadRequest)?;
    let mut builder = client().request(method, url);
    for (k, v) in headers {
        // Never log header values (may contain Authorization).
        builder = builder.header(k, v);
    }
    if let Some(b) = body {
        builder = builder
            .header("Content-Type", "application/json")
            .body(b);
    }
    let resp = builder.send().map_err(|_| ApiError::Network)?;
    let status = resp.status().as_u16();
    let body = resp.text().unwrap_or_default();
    Ok(ApiResponse { status, body })
}
