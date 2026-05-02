// TudouClaw desktop floating-agent widget — Mac MVP.
//
// Lifecycle: app starts hidden (window declared visible=false in
// tauri.conf.json). Portal triggers `tudouclaw://open` to show the
// floater, `tudouclaw://hide` to dismiss. The window is never
// destroyed — show/hide toggles its visibility so position/state
// are preserved across portal sessions.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::{AppHandle, Manager};
use tauri_plugin_deep_link::DeepLinkExt;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_deep_link::init())
        .setup(|app| {
            let handle = app.handle().clone();
            app.deep_link().on_open_url(move |event| {
                for url in event.urls() {
                    handle_action(&handle, &url);
                }
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running TudouClaw desktop");
}

/// Apply a `tudouclaw://<action>` URL. Unknown actions are ignored.
fn handle_action(app: &AppHandle, url: &url::Url) {
    let Some(window) = app.get_webview_window("main") else { return; };
    let action = url.host_str().unwrap_or("").to_lowercase();
    match action.as_str() {
        "open" | "show" => {
            let _ = window.show();
            let _ = window.set_focus();
        }
        "hide" | "dismiss" => {
            let _ = window.hide();
        }
        _ => {
            // Future: tudouclaw://focus?agent=<id>, tudouclaw://chat?msg=...
        }
    }
}
