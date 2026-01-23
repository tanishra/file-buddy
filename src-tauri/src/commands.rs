use crate::{config::Config, security, AppState};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use tauri::{AppHandle, Manager, State};
use anyhow::Result;

#[derive(Debug, Serialize, Deserialize)]
pub struct VoiceCommand {
    pub text: String,
    pub timestamp: i64,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct OperationRecord {
    pub id: String,
    pub command: String,
    pub operation_type: String,
    pub files_affected: Vec<String>,
    pub timestamp: i64,
    pub status: String,
    pub can_undo: bool,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct SystemInfo {
    pub platform: String,
    pub home_dir: String,
    pub desktop_dir: String,
    pub documents_dir: String,
    pub downloads_dir: String,
}

#[tauri::command]
pub async fn execute_voice_command(
    command: String,
    state: State<'_, AppState>,
) -> Result<OperationRecord, String> {
    log::info!("Executing voice command: {}", command);

    let url = format!("{}/execute", state.python_server_url);
    let client = reqwest::Client::new();

    let response = client
        .post(&url)
        .json(&serde_json::json!({
            "command": command,
            "timestamp": chrono::Utc::now().timestamp()
        }))
        .send()
        .await
        .map_err(|e| format!("Failed to send command: {}", e))?;

    if !response.status().is_success() {
        return Err(format!("Server error: {}", response.status()));
    }

    let result: OperationRecord = response
        .json()
        .await
        .map_err(|e| format!("Failed to parse response: {}", e))?;

    Ok(result)
}

#[tauri::command]
pub async fn get_operation_history(
    limit: Option<usize>,
    state: State<'_, AppState>,
) -> Result<Vec<OperationRecord>, String> {
    let url = format!(
        "{}/history?limit={}",
        state.python_server_url,
        limit.unwrap_or(50)
    );
    let client = reqwest::Client::new();

    let response = client
        .get(&url)
        .send()
        .await
        .map_err(|e| format!("Failed to fetch history: {}", e))?;

    let history: Vec<OperationRecord> = response
        .json()
        .await
        .map_err(|e| format!("Failed to parse history: {}", e))?;

    Ok(history)
}

#[tauri::command]
pub async fn undo_operation(
    operation_id: String,
    state: State<'_, AppState>,
) -> Result<String, String> {
    let url = format!("{}/undo/{}", state.python_server_url, operation_id);
    let client = reqwest::Client::new();

    let response = client
        .post(&url)
        .send()
        .await
        .map_err(|e| format!("Failed to undo operation: {}", e))?;

    if !response.status().is_success() {
        return Err(format!("Undo failed: {}", response.status()));
    }

    Ok("Operation undone successfully".to_string())
}

#[tauri::command]
pub async fn get_settings(state: State<'_, AppState>) -> Result<Config, String> {
    let config = state.config.lock().await;
    Ok(config.clone())
}

#[tauri::command]
pub async fn update_settings(
    new_config: Config,
    state: State<'_, AppState>,
) -> Result<(), String> {
    let mut config = state.config.lock().await;
    *config = new_config.clone();
    new_config
        .save()
        .map_err(|e| format!("Failed to save config: {}", e))?;
    Ok(())
}

#[tauri::command]
pub async fn check_python_server(state: State<'_, AppState>) -> Result<bool, String> {
    let url = format!("{}/health", state.python_server_url);
    let client = reqwest::Client::new();

    match client.get(&url).send().await {
        Ok(response) => Ok(response.status().is_success()),
        Err(_) => Ok(false),
    }
}

#[tauri::command]
pub async fn start_python_server(app: AppHandle) -> Result<(), String> {
    ensure_python_server(&app)
        .await
        .map_err(|e| e.to_string())
}

pub async fn ensure_python_server(app: &AppHandle) -> Result<()> {
    use std::process::Command;
    use std::time::Duration;
    use tokio::time::sleep;

    // Check if server is already running
    let client = reqwest::Client::new();
    if client
        .get("http://localhost:8765/health")
        .send()
        .await
        .is_ok()
    {
        log::info!("Python server already running");
        return Ok(());
    }

    log::info!("Starting Python server...");

    // Get the resource path for the Python agent
    let resource_path = app
        .path_resolver()
        .resource_dir()
        .ok_or_else(|| anyhow::anyhow!("Failed to resolve resource directory"))?;

    let python_dir = resource_path.join("python-agent");

    // Start Python server as background process
    #[cfg(target_os = "windows")]
    let python_cmd = "python";
    #[cfg(not(target_os = "windows"))]
    let python_cmd = "python3";

    Command::new(python_cmd)
        .arg("server.py")
        .current_dir(&python_dir)
        .spawn()
        .map_err(|e| anyhow::anyhow!("Failed to start Python server: {}", e))?;

    // Wait for server to start
    for _ in 0..30 {
        sleep(Duration::from_millis(500)).await;
        if client
            .get("http://localhost:8765/health")
            .send()
            .await
            .is_ok()
        {
            log::info!("Python server started successfully");
            return Ok(());
        }
    }

    Err(anyhow::anyhow!("Python server failed to start within 15 seconds"))
}

#[tauri::command]
pub fn get_allowed_directories(state: State<'_, AppState>) -> Result<Vec<String>, String> {
    let config = tauri::async_runtime::block_on(state.config.lock());
    Ok(config
        .allowed_directories
        .iter()
        .map(|p| p.display().to_string())
        .collect())
}

#[tauri::command]
pub fn add_allowed_directory(path: String, state: State<'_, AppState>) -> Result<(), String> {
    let mut config = tauri::async_runtime::block_on(state.config.lock());
    let path_buf = PathBuf::from(&path);
    if !config.allowed_directories.contains(&path_buf) {
        config.allowed_directories.push(path_buf);
        config.save().map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
pub fn remove_allowed_directory(path: String, state: State<'_, AppState>) -> Result<(), String> {
    let mut config = tauri::async_runtime::block_on(state.config.lock());
    let path_buf = PathBuf::from(&path);
    config.allowed_directories.retain(|p| p != &path_buf);
    config.save().map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn validate_file_path(path: String, state: State<'_, AppState>) -> Result<bool, String> {
    let config = tauri::async_runtime::block_on(state.config.lock());
    let path_buf = PathBuf::from(&path);
    Ok(security::validate_path(&path_buf, &config.allowed_directories))
}

#[tauri::command]
pub fn get_system_info() -> Result<SystemInfo, String> {
    use directories::UserDirs;

    let user_dirs = UserDirs::new().ok_or("Failed to get user directories")?;

    Ok(SystemInfo {
        platform: std::env::consts::OS.to_string(),
        home_dir: user_dirs
            .home_dir()
            .to_str()
            .unwrap_or("")
            .to_string(),
        desktop_dir: user_dirs
            .desktop_dir()
            .and_then(|p| p.to_str())
            .unwrap_or("")
            .to_string(),
        documents_dir: user_dirs
            .document_dir()
            .and_then(|p| p.to_str())
            .unwrap_or("")
            .to_string(),
        downloads_dir: user_dirs
            .download_dir()
            .and_then(|p| p.to_str())
            .unwrap_or("")
            .to_string(),
    })
}