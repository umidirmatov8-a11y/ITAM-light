//! Значок в области уведомлений (трее): показывает, что программа запущена,
//! открывает панель по щелчку и даёт пункт «Выход».

#[derive(Clone, Copy, Debug, PartialEq)]
#[cfg_attr(not(windows), allow(dead_code))]
pub enum Action {
    Show,
    Quit,
}

#[cfg(windows)]
mod imp {
    use super::Action;
    use tray_icon::menu::{Menu, MenuEvent, MenuItem, PredefinedMenuItem};
    use tray_icon::{
        Icon, MouseButton, MouseButtonState, TrayIcon, TrayIconBuilder, TrayIconEvent,
    };

    const SHOW_ID: &str = "show";
    const QUIT_ID: &str = "quit";

    /// Создаёт значок. Вызывать из главного потока (в нём работает цикл сообщений окна).
    /// Возвращённое значение нужно хранить: значок исчезает вместе с ним.
    pub fn create() -> Result<Box<dyn std::any::Any>, String> {
        let rgba = include_bytes!("../assets/tray_rgba.bin").to_vec();
        let icon = Icon::from_rgba(rgba, 32, 32).map_err(|e| e.to_string())?;
        let menu = Menu::new();
        menu.append_items(&[
            &MenuItem::with_id(SHOW_ID, "Открыть планировщик", true, None),
            &PredefinedMenuItem::separator(),
            &MenuItem::with_id(QUIT_ID, "Выход", true, None),
        ])
        .map_err(|e| e.to_string())?;
        let tray: TrayIcon = TrayIconBuilder::new()
            .with_icon(icon)
            .with_tooltip("DayPlanner — планировщик задач на день")
            .with_menu(Box::new(menu))
            .with_menu_on_left_click(false)
            .build()
            .map_err(|e| e.to_string())?;
        Ok(Box::new(tray))
    }

    /// Очередное действие пользователя со значком, если оно было. Можно звать из любого потока.
    pub fn poll() -> Option<Action> {
        if let Ok(event) = MenuEvent::receiver().try_recv() {
            return match event.id.0.as_str() {
                SHOW_ID => Some(Action::Show),
                QUIT_ID => Some(Action::Quit),
                _ => None,
            };
        }
        while let Ok(event) = TrayIconEvent::receiver().try_recv() {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                return Some(Action::Show);
            }
        }
        None
    }
}

#[cfg(not(windows))]
mod imp {
    use super::Action;
    pub fn create() -> Result<Box<dyn std::any::Any>, String> {
        Err("значок в трее есть только в Windows".into())
    }
    pub fn poll() -> Option<Action> {
        None
    }
}

pub use imp::*;
