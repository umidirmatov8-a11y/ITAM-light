//! DayPlanner — планировщик задач на день.
//! Панель выезжает сверху, когда курсор подведён к верхнему краю экрана.

#![cfg_attr(all(windows, not(debug_assertions)), windows_subsystem = "windows")]

mod edge;
mod model;
mod platform;
mod report;
mod ui;

use eframe::egui;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

pub const PANEL_SIZE: [f32; 2] = [760.0, 580.0];
/// Место скрытой панели: вне любого монитора (как у свёрнутых окон Windows).
const PARKED: (i32, i32) = (-32000, -32000);

/// Состояние, общее для интерфейса и фонового потока.
pub struct Shared {
    /// Панель закреплена пользователем.
    pub pinned: AtomicBool,
    /// Панель сейчас показана (хотя бы частично).
    pub open: AtomicBool,
}

fn main() -> eframe::Result {
    if !platform::single_instance() {
        return Ok(());
    }
    let store = Arc::new(Mutex::new(model::Store::load(
        &platform::data_dir().join("tasks.json"),
    )));
    let shared = Arc::new(Shared {
        pinned: AtomicBool::new(false),
        // Вне Windows панель — обычное окно, оно всегда «открыто».
        open: AtomicBool::new(!cfg!(windows)),
    });

    let mut viewport = egui::ViewportBuilder::default()
        .with_title("DayPlanner")
        .with_inner_size(PANEL_SIZE)
        .with_resizable(false);
    if cfg!(windows) {
        viewport = viewport
            .with_decorations(false)
            .with_always_on_top()
            .with_taskbar(false)
            .with_position([0.0, -4000.0]); // до первого кадра держим за экраном
    }
    let options = eframe::NativeOptions {
        viewport,
        ..Default::default()
    };

    eframe::run_native(
        "DayPlanner",
        options,
        Box::new(move |cc| {
            ui::apply_style(&cc.egui_ctx);
            let hwnd = window_handle(cc);
            let (ctx, st, sh) = (cc.egui_ctx.clone(), store.clone(), shared.clone());
            std::thread::spawn(move || background(ctx, st, sh, hwnd));
            Ok(Box::new(ui::PlannerApp::new(store, shared)))
        }),
    )
}

fn window_handle(cc: &eframe::CreationContext<'_>) -> isize {
    use raw_window_handle::{HasWindowHandle, RawWindowHandle};
    match cc.window_handle().map(|h| h.as_raw()) {
        Ok(RawWindowHandle::Win32(h)) => h.hwnd.get(),
        _ => 0,
    }
}

/// Фоновый поток: следит за курсором, двигает панель и ведёт расписание отчётов.
/// Работает независимо от отрисовки, поэтому отчёт пишется и при скрытой панели.
fn background(
    ctx: egui::Context,
    store: Arc<Mutex<model::Store>>,
    shared: Arc<Shared>,
    hwnd: isize,
) {
    let started = Instant::now();
    let mut trigger = edge::Trigger::default();
    let mut slide = edge::Slide::default();
    let mut last_tick = Instant::now();
    let mut last_schedule: Option<Instant> = None;
    let mut last_clip = (0, 0, i32::MAX);
    let mut home = platform::monitor_at(0, 0);
    let mut last_pos = (i32::MIN, i32::MIN);
    let mut prev_foreground = 0isize;
    let mut was_open = false;
    if hwnd != 0 {
        platform::style_panel(hwnd);
    }

    loop {
        let now = Instant::now();
        let dt_ms = now.duration_since(last_tick).as_secs_f32() * 1000.0;
        last_tick = now;

        // Отчёты: раз в секунду проверяем конец дня и пропущенные дни.
        if last_schedule.is_none_or(|t| now.duration_since(t) >= Duration::from_secs(1)) {
            last_schedule = Some(now);
            let mut s = store.lock().unwrap();
            let local = chrono::Local::now().naive_local();
            if report::run_schedule(&mut s, local, &report::report_dir()) {
                let _ = s.save();
                ctx.request_repaint();
            }
        }

        let mut moving = false;
        if let Some(rect) = platform::window_rect(hwnd).filter(|_| hwnd != 0) {
            let (w, h) = (rect.width(), rect.height());
            let cursor = platform::cursor();
            // Пока панель полностью скрыта, она «переезжает» на монитор, где курсор;
            // показанная панель остаётся на том мониторе, где открылась.
            if !was_open && !slide.is_moving() {
                home = platform::monitor_at(cursor.0, cursor.1);
            }
            let x = home.left + (home.width() - w) / 2;
            let shown = (slide.position() * h as f32).round() as i32;
            let want_open = trigger.update(&edge::Input {
                now_ms: started.elapsed().as_millis() as u64,
                cursor,
                lmb: platform::lmb_down(),
                screen: home,
                edge_free: !platform::on_any_monitor(cursor.0, home.top - 1),
                panel: edge::Rect {
                    left: x,
                    top: home.top,
                    right: x + w,
                    bottom: home.top + shown,
                },
                pinned: shared.pinned.load(Ordering::Relaxed),
            });

            if want_open && !was_open {
                prev_foreground = platform::foreground();
                shared.open.store(true, Ordering::Relaxed);
                ctx.request_repaint();
            }
            let p = slide.step(want_open, dt_ms);
            moving = slide.is_moving();
            let hidden_top = ((1.0 - p) * h as f32).round() as i32;
            // Полностью скрытая панель лежит за пределами всех мониторов.
            let pos = if p <= 0.0 {
                PARKED
            } else {
                (x, home.top - hidden_top)
            };
            // При выезде сначала обрезаем, потом двигаем; при скрытии — наоборот,
            // чтобы над краем монитора никогда не показалась лишняя полоса.
            let clip = (w, h, hidden_top);
            if clip != last_clip && hidden_top >= last_clip.2 {
                platform::clip_panel(hwnd, w, h, 18, hidden_top);
            }
            if pos != last_pos {
                last_pos = pos;
                platform::move_window(hwnd, pos.0, pos.1);
            }
            if clip != last_clip && hidden_top < last_clip.2 {
                platform::clip_panel(hwnd, w, h, 18, hidden_top);
            }
            last_clip = clip;
            if !want_open && !moving && shared.open.swap(false, Ordering::Relaxed) {
                // Возвращаем фокус окну, с которым работали до открытия панели.
                if platform::foreground() == hwnd && prev_foreground != 0 {
                    platform::set_foreground(prev_foreground);
                }
                ctx.request_repaint();
            }
            was_open = want_open;
        }

        std::thread::sleep(Duration::from_millis(if moving { 6 } else { 15 }));
    }
}
