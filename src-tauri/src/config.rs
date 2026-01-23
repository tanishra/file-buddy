use anyhow::Result;
use directories::ProjectDirs;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    pub allowed_directories: Vec<PathBuf>,
    pub hotkey: String,
    pub auto_start: bool,
    pub confirmation_required: bool,
    pub voice_activation_sensitivity: f32,
    pub theme: String,
    pub minimize_to_tray: bool,
    pub show_notifications: bool,
    pub memory_retention_days: u32,
}

impl Default for Config {
    fn default() -> Self {
        use directories::UserDirs;
        let user_dirs = UserDirs::new();

        let mut allowed_dirs = Vec::new();
        if let Some(dirs) = user_dirs {
            if let Some(desktop) = dirs.desktop_dir() {
                allowed_dirs.push(desktop.to_path_buf());
            }
            if let Some(documents) = dirs.document_dir() {
                allowed_dirs.push(documents.to_path_buf());
            }
            if let Some(downloads) = dirs.download_dir() {
                allowed_dirs.push(downloads.to_path_buf());
            }
        }

        Self {
            allowed_directories: allowed_dirs,
            hotkey: "Ctrl+Shift+F".to_string(),
            auto_start: false,
            confirmation_required: true,
            voice_activation_sensitivity: 0.7,
            theme: "system".to_string(),
            minimize_to_tray: true,
            show_notifications: true,
            memory_retention_days: 90,
        }
    }
}

impl Config {
    pub fn load() -> Result<Self> {
        let config_path = Self::config_path()?;

        if config_path.exists() {
            let content = fs::read_to_string(&config_path)?;
            let config: Config = serde_json::from_str(&content)?;
            Ok(config)
        } else {
            let config = Config::default();
            config.save()?;
            Ok(config)
        }
    }

    pub fn save(&self) -> Result<()> {
        let config_path = Self::config_path()?;

        if let Some(parent) = config_path.parent() {
            fs::create_dir_all(parent)?;
        }

        let content = serde_json::to_string_pretty(self)?;
        fs::write(config_path, content)?;

        Ok(())
    }

    fn config_path() -> Result<PathBuf> {
        let proj_dirs = ProjectDirs::from("com", "filebuddy", "FileBuddy")
            .ok_or_else(|| anyhow::anyhow!("Failed to get project directories"))?;

        let config_dir = proj_dirs.config_dir();
        Ok(config_dir.join("config.json"))
    }

    pub fn data_dir() -> Result<PathBuf> {
        let proj_dirs = ProjectDirs::from("com", "filebuddy", "FileBuddy")
            .ok_or_else(|| anyhow::anyhow!("Failed to get project directories"))?;

        let data_dir = proj_dirs.data_dir();
        fs::create_dir_all(data_dir)?;
        Ok(data_dir.to_path_buf())
    }
}