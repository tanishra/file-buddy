use tauri::{AppHandle, Manager};
use global_hotkey::{
    hotkey::{Code, HotKey, Modifiers},
    GlobalHotKeyEvent, GlobalHotKeyManager,
};
use std::sync::Arc;

pub fn register_hotkey(app_handle: AppHandle) {
    tauri::async_runtime::spawn(async move {
        if let Err(e) = setup_hotkey(app_handle).await {
            log::error!("Failed to register hotkey: {}", e);
        }
    });
}

async fn setup_hotkey(app_handle: AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let manager = GlobalHotKeyManager::new()?;

    // Register Ctrl+Shift+F
    let hotkey = HotKey::new(
        Some(Modifiers::CONTROL | Modifiers::SHIFT),
        Code::KeyF,
    );

    manager.register(hotkey)?;

    log::info!("Registered global hotkey: Ctrl+Shift+F");

    // Listen for hotkey events
    let receiver = GlobalHotKeyEvent::receiver();

    tauri::async_runtime::spawn(async move {
        loop {
            if let Ok(event) = receiver.try_recv() {
                log::debug!("Hotkey pressed: {:?}", event);
                
                // Show the main window and trigger voice activation
                if let Some(window) = app_handle.get_window("main") {
                    if let Err(e) = window.show() {
                        log::error!("Failed to show window: {}", e);
                    }
                    if let Err(e) = window.set_focus() {
                        log::error!("Failed to focus window: {}", e);
                    }
                    
                    // Emit event to frontend to start voice listening
                    if let Err(e) = window.emit("hotkey-activated", {}) {
                        log::error!("Failed to emit hotkey event: {}", e);
                    }
                }
            }
            
            tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;
        }
    });

    Ok(())
}

pub fn update_tray_status(app_handle: &AppHandle, status: &str) {
    if let Some(tray) = app_handle.tray_handle() {
        use tauri::{CustomMenuItem, SystemTrayMenu, SystemTrayMenuItem};

        let status_item = CustomMenuItem::new("status".to_string(), status).disabled();
        let quit = CustomMenuItem::new("quit".to_string(), "Quit FileBuddy");
        let show = CustomMenuItem::new("show".to_string(), "Show Window");
        let settings = CustomMenuItem::new("settings".to_string(), "Settings");

        let menu = SystemTrayMenu::new()
            .add_item(status_item)
            .add_native_item(SystemTrayMenuItem::Separator)
            .add_item(show)
            .add_item(settings)
            .add_native_item(SystemTrayMenuItem::Separator)
            .add_item(quit);

        if let Err(e) = tray.set_menu(menu) {
            log::error!("Failed to update tray menu: {}", e);
        }
    }
}