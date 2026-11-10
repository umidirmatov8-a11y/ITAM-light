//! Всё, что зависит от Windows: курсор, кнопка мыши, положение окна.
//! Для остальных систем — заглушки, чтобы логику и интерфейс можно было собирать и проверять.

use crate::edge::Rect;
use std::path::PathBuf;

#[cfg(windows)]
mod imp {
    use super::Rect;
    use std::ffi::c_void;
    use windows_sys::Win32::Foundation::{GetLastError, ERROR_ALREADY_EXISTS, POINT, RECT};
    use windows_sys::Win32::Graphics::Gdi::{
        CombineRgn, CreateRectRgn, CreateRoundRectRgn, DeleteObject, GetMonitorInfoW,
        MonitorFromPoint, SetWindowRgn, MONITORINFO, MONITOR_DEFAULTTONEAREST,
        MONITOR_DEFAULTTONULL, RGN_AND,
    };
    use windows_sys::Win32::System::Threading::CreateMutexW;
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
        GetAsyncKeyState, VK_LBUTTON, VK_RBUTTON,
    };
    use windows_sys::Win32::UI::WindowsAndMessaging::*;

    fn h(hwnd: isize) -> *mut c_void {
        hwnd as *mut c_void
    }

    pub fn cursor() -> (i32, i32) {
        let mut p = POINT { x: 0, y: 0 };
        unsafe { GetCursorPos(&mut p) };
        (p.x, p.y)
    }

    /// Зажата ли основная кнопка мыши (с учётом настройки «для левши»).
    pub fn lmb_down() -> bool {
        unsafe {
            let vk = if GetSystemMetrics(SM_SWAPBUTTON) != 0 {
                VK_RBUTTON
            } else {
                VK_LBUTTON
            };
            (GetAsyncKeyState(vk as i32) as u16 & 0x8000) != 0
        }
    }

    /// Монитор, на котором находится точка (или ближайший к ней).
    pub fn monitor_at(x: i32, y: i32) -> Rect {
        unsafe {
            let monitor = MonitorFromPoint(POINT { x, y }, MONITOR_DEFAULTTONEAREST);
            let mut info: MONITORINFO = std::mem::zeroed();
            info.cbSize = std::mem::size_of::<MONITORINFO>() as u32;
            if GetMonitorInfoW(monitor, &mut info) == 0 {
                // Не должно случаться; тогда считаем экраном основной монитор.
                return Rect {
                    left: 0,
                    top: 0,
                    right: GetSystemMetrics(SM_CXSCREEN),
                    bottom: GetSystemMetrics(SM_CYSCREEN),
                };
            }
            let r = info.rcMonitor;
            Rect {
                left: r.left,
                top: r.top,
                right: r.right,
                bottom: r.bottom,
            }
        }
    }

    /// Попадает ли точка на какой-нибудь монитор.
    pub fn on_any_monitor(x: i32, y: i32) -> bool {
        unsafe { !MonitorFromPoint(POINT { x, y }, MONITOR_DEFAULTTONULL).is_null() }
    }

    pub fn window_rect(hwnd: isize) -> Option<Rect> {
        let mut r = RECT {
            left: 0,
            top: 0,
            right: 0,
            bottom: 0,
        };
        if unsafe { GetWindowRect(h(hwnd), &mut r) } == 0 {
            return None;
        }
        Some(Rect {
            left: r.left,
            top: r.top,
            right: r.right,
            bottom: r.bottom,
        })
    }

    pub fn move_window(hwnd: isize, x: i32, y: i32) {
        unsafe {
            SetWindowPos(
                h(hwnd),
                HWND_TOPMOST,
                x,
                y,
                0,
                0,
                SWP_NOSIZE | SWP_NOACTIVATE,
            );
        }
    }

    /// Убирает окно из Alt+Tab и панели задач.
    pub fn style_panel(hwnd: isize) {
        unsafe {
            let ex = GetWindowLongPtrW(h(hwnd), GWL_EXSTYLE);
            SetWindowLongPtrW(
                h(hwnd),
                GWL_EXSTYLE,
                (ex | WS_EX_TOOLWINDOW as isize) & !(WS_EX_APPWINDOW as isize),
            );
        }
    }

    /// Скругляет нижние углы и обрезает окно сверху на `hidden_top` пикселей:
    /// ещё не выехавшая часть не видна, даже если над монитором стоит другой монитор.
    pub fn clip_panel(hwnd: isize, w: i32, height: i32, radius: i32, hidden_top: i32) {
        unsafe {
            let rgn = CreateRoundRectRgn(0, -radius, w + 1, height + 1, radius * 2, radius * 2);
            let visible = CreateRectRgn(0, hidden_top, w, height);
            CombineRgn(rgn, rgn, visible, RGN_AND);
            DeleteObject(visible);
            SetWindowRgn(h(hwnd), rgn, 1); // регионом дальше владеет система
        }
    }

    pub fn foreground() -> isize {
        unsafe { GetForegroundWindow() as isize }
    }

    pub fn set_foreground(hwnd: isize) {
        unsafe {
            if IsWindow(h(hwnd)) != 0 {
                SetForegroundWindow(h(hwnd));
            }
        }
    }

    /// false — программа уже запущена.
    pub fn single_instance() -> bool {
        let name: Vec<u16> = "Local\\DayPlanner.SingleInstance\0"
            .encode_utf16()
            .collect();
        unsafe {
            let handle = CreateMutexW(std::ptr::null(), 0, name.as_ptr());
            // Дескриптор намеренно не закрываем: он живёт до конца процесса.
            !(handle.is_null() || GetLastError() == ERROR_ALREADY_EXISTS)
        }
    }
}

#[cfg(not(windows))]
mod imp {
    use super::Rect;
    pub fn cursor() -> (i32, i32) {
        (0, 0)
    }
    pub fn lmb_down() -> bool {
        false
    }
    pub fn monitor_at(_: i32, _: i32) -> Rect {
        Rect {
            left: 0,
            top: 0,
            right: 1920,
            bottom: 1080,
        }
    }
    pub fn on_any_monitor(_: i32, _: i32) -> bool {
        true
    }
    pub fn window_rect(_: isize) -> Option<Rect> {
        None
    }
    pub fn move_window(_: isize, _: i32, _: i32) {}
    pub fn style_panel(_: isize) {}
    pub fn clip_panel(_: isize, _: i32, _: i32, _: i32, _: i32) {}
    pub fn foreground() -> isize {
        0
    }
    pub fn set_foreground(_: isize) {}
    pub fn single_instance() -> bool {
        true
    }
}

pub use imp::*;

/// Папка с данными программы: %APPDATA%\DayPlanner.
pub fn data_dir() -> PathBuf {
    if let Some(dir) = std::env::var_os("DAYPLANNER_DATA_DIR") {
        return PathBuf::from(dir);
    }
    let base = std::env::var_os("APPDATA")
        .or_else(|| std::env::var_os("XDG_DATA_HOME"))
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|h| PathBuf::from(h).join(".local/share")))
        .unwrap_or_else(|| PathBuf::from("."));
    base.join("DayPlanner")
}

pub fn open_folder(path: &std::path::Path) {
    let program = if cfg!(windows) {
        "explorer"
    } else {
        "xdg-open"
    };
    let _ = std::process::Command::new(program).arg(path).spawn();
}
