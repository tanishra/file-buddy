// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod config;
mod file_ops;
mod security;
mod tray;

use tauri::{
    CustomMenuItem, Manager, SystemTray, SystemTrayEvent, SystemTrayMenu,
    SystemTrayMenuItem, WindowEvent,
};
use log::{info, error};
use std::sync::Arc;
use tokio::sync::Mutex;

pub struct AppState {
    pub config: Arc<Mutex<config::Config>>,
    pub python_server_url: String,
}

fn main() {
    env_logger::init();
    
    info!("Starting FileBuddy desktop application");

    // Create system tray menu
    let quit = CustomMenuItem::new("quit".to_string(), "Quit FileBuddy");
    let show = CustomMenuItem::new("show".to_string(), "Show Window");
    let settings = CustomMenuItem::new("settings".to_string(), "Settings");
    let status = CustomMenuItem::new("status".to_string(), "🎤 Ready").disabled();
    
    let tray_menu = SystemTrayMenu::new()
        .add_item(status)
        .add_native_item(SystemTrayMenuItem::Separator)
        .add_item(show)
        .add_item(settings)
        .add_native_item(SystemTrayMenuItem::Separator)
        .add_item(quit);

    let system_tray = SystemTray::new().with_menu(tray_menu);

    // Initialize app state
    let config = config::Config::load().unwrap_or_default();
    let app_state = AppState {
        config: Arc::new(Mutex::new(config)),
        python_server_url: "http://localhost:8765".to_string(),
    };

    tauri::Builder::default()
        .manage(app_state)
        .system_tray(system_tray)
        .on_system_tray_event(|app, event| match event {
            SystemTrayEvent::LeftClick {
                position: _,
                size: _,
                ..
            } => {
                let window = app.get_window("main").unwrap();
                window.show().unwrap();
                window.set_focus().unwrap();
            }
            SystemTrayEvent::MenuItemClick { id, .. } => match id.as_str() {
                "quit" => {
                    std::process::exit(0);
                }
                "show" => {
                    let window = app.get_window("main").unwrap();
                    window.show().unwrap();
                    window.set_focus().unwrap();
                }
                "settings" => {
                    let window = app.get_window("main").unwrap();
                    window.emit("open-settings", {}).unwrap();
                    window.show().unwrap();
                    window.set_focus().unwrap();
                }
                _ => {}
            },
            _ => {}
        })
        .on_window_event(|event| match event.event() {
            WindowEvent::CloseRequested { api, .. } => {
                // Hide instead of close
                event.window().hide().unwrap();
                api.prevent_close();
            }
            _ => {}
        })
        .invoke_handler(tauri::generate_handler![
            commands::execute_voice_command,
            commands::get_operation_history,
            commands::undo_operation,
            commands::get_settings,
            commands::update_settings,
            commands::check_python_server,
            commands::start_python_server,
            commands::get_allowed_directories,
            commands::add_allowed_directory,
            commands::remove_allowed_directory,
            commands::validate_file_path,
            commands::get_system_info,
        ])
        .setup(|app| {
            // Start Python server in background
            let app_handle = app.handle();
            tauri::async_runtime::spawn(async move {
                if let Err(e) = commands::ensure_python_server(&app_handle).await {
                    error!("Failed to start Python server: {}", e);
                }
            });

            // Register global hotkey (Ctrl+Shift+F)
            tray::register_hotkey(app.handle());

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}