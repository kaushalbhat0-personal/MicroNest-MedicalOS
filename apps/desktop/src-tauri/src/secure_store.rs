//! SecureTokenStore — Windows DPAPI-backed refresh token persistence.
//! Access tokens are never written to disk (held in the frontend memory only).

use std::fs;
use std::path::PathBuf;

use base64::{engine::general_purpose::STANDARD as B64, Engine};
use serde::{Deserialize, Serialize};

#[derive(Debug, thiserror::Error)]
pub enum StoreError {
    #[error("secure storage is only available on Windows")]
    #[allow(dead_code)]
    UnsupportedPlatform,
    #[error("storage failure: {0}")]
    Io(String),
    #[error("DPAPI protect failed")]
    ProtectFailed,
    #[error("DPAPI unprotect failed (profile mismatch or corrupt ciphertext)")]
    UnprotectFailed,
    #[error("no refresh token stored")]
    Missing,
    #[error("invalid ciphertext")]
    InvalidCiphertext,
}

#[derive(Debug, Serialize, Deserialize)]
struct Envelope {
    v: u8,
    ciphertext_b64: String,
}

pub fn credentials_dir() -> Result<PathBuf, StoreError> {
    if let Ok(override_dir) = std::env::var("HOS_CREDENTIALS_DIR") {
        let dir = PathBuf::from(override_dir);
        fs::create_dir_all(&dir).map_err(|e| StoreError::Io(e.to_string()))?;
        return Ok(dir);
    }
    let base = std::env::var_os("LOCALAPPDATA")
        .map(PathBuf::from)
        .ok_or_else(|| StoreError::Io("LOCALAPPDATA missing".into()))?;
    let dir = base.join("HealthcareOS").join("credentials");
    fs::create_dir_all(&dir).map_err(|e| StoreError::Io(e.to_string()))?;
    Ok(dir)
}

fn refresh_path() -> Result<PathBuf, StoreError> {
    Ok(credentials_dir()?.join("refresh.dpapi"))
}

#[cfg(windows)]
mod dpapi {
    use super::StoreError;
    use std::ptr;
    use windows_sys::Win32::Foundation::{LocalFree, BOOL, HANDLE};
    use windows_sys::Win32::Security::Cryptography::{
        CryptProtectData, CryptUnprotectData, CRYPT_INTEGER_BLOB,
    };

    pub fn protect(plain: &[u8]) -> Result<Vec<u8>, StoreError> {
        let mut in_blob = CRYPT_INTEGER_BLOB {
            cbData: plain.len() as u32,
            pbData: plain.as_ptr() as *mut u8,
        };
        let mut out_blob = CRYPT_INTEGER_BLOB {
            cbData: 0,
            pbData: ptr::null_mut(),
        };
        let ok: BOOL = unsafe {
            CryptProtectData(
                &mut in_blob,
                ptr::null(),
                ptr::null_mut(),
                ptr::null_mut(),
                ptr::null_mut(),
                0,
                &mut out_blob,
            )
        };
        if ok == 0 {
            return Err(StoreError::ProtectFailed);
        }
        let slice =
            unsafe { std::slice::from_raw_parts(out_blob.pbData, out_blob.cbData as usize) };
        let data = slice.to_vec();
        unsafe {
            LocalFree(out_blob.pbData as HANDLE);
        }
        Ok(data)
    }

    pub fn unprotect(cipher: &[u8]) -> Result<Vec<u8>, StoreError> {
        let mut in_blob = CRYPT_INTEGER_BLOB {
            cbData: cipher.len() as u32,
            pbData: cipher.as_ptr() as *mut u8,
        };
        let mut out_blob = CRYPT_INTEGER_BLOB {
            cbData: 0,
            pbData: ptr::null_mut(),
        };
        let ok: BOOL = unsafe {
            CryptUnprotectData(
                &mut in_blob,
                ptr::null_mut(),
                ptr::null_mut(),
                ptr::null_mut(),
                ptr::null_mut(),
                0,
                &mut out_blob,
            )
        };
        if ok == 0 {
            return Err(StoreError::UnprotectFailed);
        }
        let slice =
            unsafe { std::slice::from_raw_parts(out_blob.pbData, out_blob.cbData as usize) };
        let data = slice.to_vec();
        unsafe {
            LocalFree(out_blob.pbData as HANDLE);
        }
        Ok(data)
    }
}

#[cfg(not(windows))]
mod dpapi {
    use super::StoreError;
    pub fn protect(_plain: &[u8]) -> Result<Vec<u8>, StoreError> {
        Err(StoreError::UnsupportedPlatform)
    }
    pub fn unprotect(_cipher: &[u8]) -> Result<Vec<u8>, StoreError> {
        Err(StoreError::UnsupportedPlatform)
    }
}

pub fn store_refresh_token(token: &str) -> Result<(), StoreError> {
    if token.is_empty() {
        return Err(StoreError::Io("empty refresh token".into()));
    }
    let sealed = dpapi::protect(token.as_bytes())?;
    let env = Envelope {
        v: 1,
        ciphertext_b64: B64.encode(sealed),
    };
    let path = refresh_path()?;
    let json = serde_json::to_vec(&env).map_err(|e| StoreError::Io(e.to_string()))?;
    // Never write plaintext token. Envelope holds DPAPI ciphertext only.
    fs::write(&path, json).map_err(|e| StoreError::Io(e.to_string()))?;
    Ok(())
}

pub fn retrieve_refresh_token() -> Result<String, StoreError> {
    let path = refresh_path()?;
    if !path.exists() {
        return Err(StoreError::Missing);
    }
    let raw = fs::read(&path).map_err(|e| StoreError::Io(e.to_string()))?;
    let env: Envelope =
        serde_json::from_slice(&raw).map_err(|_| StoreError::InvalidCiphertext)?;
    if env.v != 1 {
        return Err(StoreError::InvalidCiphertext);
    }
    let cipher = B64
        .decode(env.ciphertext_b64.as_bytes())
        .map_err(|_| StoreError::InvalidCiphertext)?;
    if cipher.is_empty() {
        return Err(StoreError::InvalidCiphertext);
    }
    let plain = dpapi::unprotect(&cipher)?;
    String::from_utf8(plain).map_err(|_| StoreError::InvalidCiphertext)
}

pub fn delete_refresh_token() -> Result<(), StoreError> {
    let path = refresh_path()?;
    if path.exists() {
        fs::remove_file(&path).map_err(|e| StoreError::Io(e.to_string()))?;
    }
    Ok(())
}

pub fn clear_session() -> Result<(), StoreError> {
    delete_refresh_token()
}

#[cfg(all(test, windows))]
mod tests {
    use super::*;
    use std::sync::Mutex;

    static LOCK: Mutex<()> = Mutex::new(());

    fn with_temp_dir<F: FnOnce()>(name: &str, f: F) {
        let _guard = LOCK.lock().unwrap();
        let dir = std::env::temp_dir().join(format!("hos-dpapi-test-{name}"));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        // SAFETY: single-threaded via LOCK; test-only env override.
        unsafe { std::env::set_var("HOS_CREDENTIALS_DIR", &dir) };
        f();
        unsafe { std::env::remove_var("HOS_CREDENTIALS_DIR") };
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn dpapi_round_trip_and_cleanup() {
        with_temp_dir("roundtrip", || {
            let token = "01deadbeef-session.secret-value-not-logged";
            store_refresh_token(token).expect("store");
            let path = refresh_path().unwrap();
            let disk = std::fs::read(&path).unwrap();
            let disk_txt = String::from_utf8_lossy(&disk);
            assert!(
                !disk_txt.contains(token),
                "plaintext refresh must not appear on disk"
            );
            let got = retrieve_refresh_token().expect("retrieve");
            assert_eq!(got, token);
            clear_session().expect("clear");
            assert!(matches!(
                retrieve_refresh_token().unwrap_err(),
                StoreError::Missing
            ));
        });
    }

    #[test]
    fn invalid_ciphertext_fails() {
        with_temp_dir("badcipher", || {
            let path = refresh_path().unwrap();
            std::fs::write(&path, b"{\"v\":1,\"ciphertext_b64\":\"@@@\"}").unwrap();
            assert!(matches!(
                retrieve_refresh_token().unwrap_err(),
                StoreError::InvalidCiphertext | StoreError::UnprotectFailed
            ));
            let _ = delete_refresh_token();
        });
    }
}
