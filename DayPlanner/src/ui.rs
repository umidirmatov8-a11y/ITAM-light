//! Интерфейс панели.

use crate::model::{Store, Task};
use crate::{platform, report, Shared};
use chrono::{Datelike, Duration as ChronoDuration, NaiveDate, NaiveDateTime, Timelike};
use eframe::egui::{self, Align, Color32, CornerRadius, Layout, RichText, Stroke};
use std::sync::atomic::Ordering;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

const BG: Color32 = Color32::from_rgb(28, 28, 32);
const CARD: Color32 = Color32::from_rgb(42, 42, 48);
const ACCENT: Color32 = Color32::from_rgb(10, 132, 255);
const GREEN: Color32 = Color32::from_rgb(48, 209, 88);
const RED: Color32 = Color32::from_rgb(255, 69, 58);
const ORANGE: Color32 = Color32::from_rgb(255, 159, 10);
const MUTED: Color32 = Color32::from_rgb(152, 152, 160);

/// Кнопка подтверждения не реагирует первые мгновения — двойной клик ничего не подтвердит.
const CONFIRM_GUARD: Duration = Duration::from_millis(450);

const MONTHS: [&str; 12] = [
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
];

pub fn apply_style(ctx: &egui::Context) {
    let mut visuals = egui::Visuals::dark();
    visuals.panel_fill = BG;
    visuals.override_text_color = Some(Color32::from_rgb(235, 235, 240));
    visuals.selection.bg_fill = ACCENT;
    visuals.extreme_bg_color = Color32::from_rgb(20, 20, 23);
    for w in [
        &mut visuals.widgets.noninteractive,
        &mut visuals.widgets.inactive,
        &mut visuals.widgets.hovered,
        &mut visuals.widgets.active,
        &mut visuals.widgets.open,
    ] {
        w.corner_radius = CornerRadius::same(8);
    }
    ctx.set_theme(egui::Theme::Dark);
    ctx.set_visuals(visuals);
    ctx.all_styles_mut(|s| {
        for font in s.text_styles.values_mut() {
            font.size *= 1.18;
        }
        s.spacing.item_spacing = egui::vec2(8.0, 8.0);
        s.spacing.button_padding = egui::vec2(10.0, 5.0);
    });
}

#[derive(Clone, Copy, PartialEq)]
enum Confirm {
    Done(u64),
    Delete(u64),
    Quit,
}

pub struct PlannerApp {
    store: Arc<Mutex<Store>>,
    shared: Arc<Shared>,
    title: String,
    date: NaiveDate,
    hour: u32,
    minute: u32,
    confirm: Option<(Confirm, Instant)>,
    status: Option<(String, Instant)>,
    /// Значок в трее: живёт, пока жива программа.
    _tray: Option<Box<dyn std::any::Any>>,
}

fn now() -> NaiveDateTime {
    chrono::Local::now().naive_local()
}

/// Срок по умолчанию: ближайший целый час.
fn default_due(now: NaiveDateTime) -> (NaiveDate, u32) {
    if now.hour() >= 23 {
        (now.date() + ChronoDuration::days(1), 9)
    } else {
        (now.date(), now.hour() + 1)
    }
}

fn days_in_month(year: i32, month: u32) -> u32 {
    let (y, m) = if month == 12 {
        (year + 1, 1)
    } else {
        (year, month + 1)
    };
    NaiveDate::from_ymd_opt(y, m, 1)
        .unwrap()
        .pred_opt()
        .unwrap()
        .day()
}

fn two_digits(ui: &mut egui::Ui, value: &mut u32, max: u32) {
    ui.add(
        egui::DragValue::new(value)
            .range(0..=max)
            .speed(0.15)
            .custom_formatter(|n, _| format!("{:02}", n as u32)),
    );
}

impl PlannerApp {
    pub fn new(
        store: Arc<Mutex<Store>>,
        shared: Arc<Shared>,
        tray: Option<Box<dyn std::any::Any>>,
    ) -> Self {
        let (date, hour) = default_due(now());
        PlannerApp {
            store,
            shared,
            title: String::new(),
            date,
            hour,
            minute: 0,
            confirm: None,
            status: None,
            _tray: tray,
        }
    }

    /// Меняет задачи, сохраняет файл и при необходимости обновляет уже записанный отчёт.
    fn mutate(&mut self, f: impl FnOnce(&mut Store, NaiveDateTime)) {
        let t = now();
        let mut s = self.store.lock().unwrap();
        f(&mut s, t);
        if let Err(e) = s.save() {
            self.status = Some((format!("Не удалось сохранить задачи: {e}"), Instant::now()));
        }
        report::refresh_if_reported(&s, t, &report::report_dir());
    }

    fn add_task(&mut self) {
        if self.title.trim().is_empty() {
            self.status = Some(("Введите название задачи".into(), Instant::now()));
            return;
        }
        let due = self.date.and_hms_opt(self.hour, self.minute, 0).unwrap();
        let title = std::mem::take(&mut self.title);
        self.mutate(|s, t| {
            s.add(&title, due, t);
        });
    }

    fn header(&mut self, ui: &mut egui::Ui, t: NaiveDateTime) {
        ui.horizontal(|ui| {
            ui.label(
                RichText::new(t.format("%H:%M").to_string())
                    .size(34.0)
                    .strong(),
            );
            ui.add_space(6.0);
            ui.vertical(|ui| {
                ui.add_space(4.0);
                ui.label(RichText::new("Планировщик на день").strong());
                ui.label(
                    RichText::new(format!(
                        "{}, {} {} {}",
                        report::weekday_ru(t.date()),
                        t.day(),
                        MONTHS[t.month0() as usize],
                        t.year()
                    ))
                    .color(MUTED),
                );
            });
            ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                if self.confirm.map(|c| c.0) == Some(Confirm::Quit) {
                    if ui.button("Отмена").clicked() {
                        self.confirm = None;
                    }
                    if self.confirm_button(ui, "Да, закрыть", RED) {
                        ui.ctx().send_viewport_cmd(egui::ViewportCommand::Close);
                    }
                    ui.label("Закрыть программу?");
                } else {
                    if ui
                        .button("Выход")
                        .on_hover_text("Закрыть планировщик")
                        .clicked()
                    {
                        self.ask(Confirm::Quit);
                    }
                    if cfg!(windows) {
                        let mut pinned = self.shared.pinned.load(Ordering::Relaxed);
                        if ui
                            .toggle_value(&mut pinned, "Закрепить")
                            .on_hover_text("Не скрывать панель, когда курсор уходит")
                            .changed()
                        {
                            self.shared.pinned.store(pinned, Ordering::Relaxed);
                        }
                    }
                }
            });
        });
    }

    fn add_form(&mut self, ui: &mut egui::Ui, t: NaiveDateTime) {
        card().show(ui, |ui| {
            ui.horizontal(|ui| {
                let button_w = 170.0;
                let edit = ui.add(
                    egui::TextEdit::singleline(&mut self.title)
                        .hint_text("Новая задача…")
                        .desired_width(ui.available_width() - button_w - 8.0),
                );
                let enter = edit.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter));
                let add = ui.add_sized(
                    [button_w, 28.0],
                    egui::Button::new(RichText::new("+ Добавить задачу").color(Color32::WHITE))
                        .fill(ACCENT),
                );
                if add.clicked() || enter {
                    self.add_task();
                    if enter {
                        edit.request_focus();
                    }
                }
            });
            ui.horizontal(|ui| {
                ui.label(RichText::new("Выполнить до:").color(MUTED));
                let (mut d, mut m, mut y) = (self.date.day(), self.date.month(), self.date.year());
                ui.add(egui::DragValue::new(&mut d).range(1..=31).speed(0.15))
                    .on_hover_text("День");
                ui.label(".");
                ui.add(
                    egui::DragValue::new(&mut m)
                        .range(1..=12)
                        .speed(0.1)
                        .custom_formatter(|n, _| format!("{:02}", n as u32)),
                )
                .on_hover_text("Месяц");
                ui.label(".");
                ui.add(egui::DragValue::new(&mut y).range(2020..=2100).speed(0.05))
                    .on_hover_text("Год");
                let d = d.min(days_in_month(y, m));
                self.date = NaiveDate::from_ymd_opt(y, m, d).unwrap_or(self.date);
                ui.label(RichText::new(short_weekday(self.date)).color(MUTED));

                ui.add_space(10.0);
                ui.label(RichText::new("в").color(MUTED));
                two_digits(ui, &mut self.hour, 23);
                ui.label(":");
                two_digits(ui, &mut self.minute, 59);

                ui.add_space(10.0);
                if ui.small_button("Сегодня").clicked() {
                    self.date = t.date();
                }
                if ui.small_button("Завтра").clicked() {
                    self.date = t.date() + ChronoDuration::days(1);
                }
            });
        });
    }

    fn ask(&mut self, what: Confirm) {
        self.confirm = Some((what, Instant::now()));
    }

    /// Кнопка «Да»: неактивна первые мгновения после появления.
    fn confirm_button(&mut self, ui: &mut egui::Ui, text: &str, color: Color32) -> bool {
        let ready = self.confirm.is_some_and(|c| c.1.elapsed() >= CONFIRM_GUARD);
        if !ready {
            ui.ctx().request_repaint_after(Duration::from_millis(50));
        }
        ui.add_enabled(
            ready,
            egui::Button::new(RichText::new(text).color(Color32::WHITE)).fill(color),
        )
        .clicked()
    }

    fn task_row(&mut self, ui: &mut egui::Ui, task: &Task, t: NaiveDateTime) {
        let done = task.done_at.is_some();
        card().show(ui, |ui| {
            ui.horizontal(|ui| {
                ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                    match self.confirm.map(|c| c.0) {
                        Some(Confirm::Done(id)) if id == task.id => {
                            if ui.button("Отмена").clicked() {
                                self.confirm = None;
                            }
                            if self.confirm_button(ui, "Да, сделано", GREEN) {
                                self.confirm = None;
                                let id = task.id;
                                self.mutate(|s, now| s.mark_done(id, now));
                            }
                            ui.label("Задача выполнена?");
                        }
                        Some(Confirm::Delete(id)) if id == task.id => {
                            if ui.button("Отмена").clicked() {
                                self.confirm = None;
                            }
                            if self.confirm_button(ui, "Да, удалить", RED) {
                                self.confirm = None;
                                let id = task.id;
                                self.mutate(|s, now| s.delete(id, now));
                            }
                            ui.label("Удалить задачу?");
                        }
                        _ => {
                            if ui.button(RichText::new("Удалить").color(RED)).clicked() {
                                self.ask(Confirm::Delete(task.id));
                            }
                            if !done && ui.button(RichText::new("Сделано").color(GREEN)).clicked()
                            {
                                self.ask(Confirm::Done(task.id));
                            }
                        }
                    }
                    ui.with_layout(Layout::top_down(Align::Min), |ui| {
                        ui.spacing_mut().item_spacing.y = 2.0;
                        let mut title = RichText::new(&task.title);
                        if done {
                            title = title.strikethrough().color(MUTED);
                        }
                        ui.add(egui::Label::new(title).wrap());
                        let due = task.due.format("%d.%m.%Y %H:%M");
                        let (text, color) = match task.done_at {
                            Some(at) => (
                                format!("срок {due} · выполнено в {}", at.format("%H:%M")),
                                MUTED,
                            ),
                            None if task.due < t => (format!("срок {due} · просрочено"), RED),
                            None => {
                                let color = if task.due.date() == t.date() {
                                    ORANGE
                                } else {
                                    MUTED
                                };
                                (format!("срок {due} · {}", time_left(task.due - t)), color)
                            }
                        };
                        ui.label(RichText::new(text).small().color(color));
                    });
                });
            });
        });
    }

    fn footer(&mut self, ui: &mut egui::Ui, t: NaiveDateTime) {
        ui.horizontal(|ui| {
            if ui
                .button("Сформировать отчёт сейчас")
                .on_hover_text("Отчёт за сегодня также создаётся автоматически в 23:59")
                .clicked()
            {
                let dir = report::report_dir();
                let s = self.store.lock().unwrap();
                let text = match report::write(&s, t.date(), t, &dir) {
                    Ok(path) => format!("Отчёт записан: {}", path.display()),
                    Err(e) => format!("Не удалось записать отчёт в {}: {e}", dir.display()),
                };
                drop(s);
                self.status = Some((text, Instant::now()));
            }
            if ui.button("Папка отчётов").clicked() {
                let dir = report::report_dir();
                let _ = std::fs::create_dir_all(&dir);
                platform::open_folder(&dir);
            }
            match &self.status {
                Some((text, at)) if at.elapsed() < Duration::from_secs(8) => {
                    ui.label(RichText::new(text).small().color(ORANGE));
                }
                _ => {
                    ui.label(
                        RichText::new(format!("Отчёты: {}", report::report_dir().display()))
                            .small()
                            .color(MUTED),
                    );
                }
            }
        });
    }
}

fn card() -> egui::Frame {
    egui::Frame::new()
        .fill(CARD)
        .corner_radius(CornerRadius::same(10))
        .inner_margin(10)
}

fn short_weekday(d: NaiveDate) -> &'static str {
    ["пн", "вт", "ср", "чт", "пт", "сб", "вс"][d.weekday().num_days_from_monday() as usize]
}

fn time_left(d: ChronoDuration) -> String {
    let m = d.num_minutes();
    if m < 60 {
        format!("осталось {} мин", m.max(1))
    } else if m < 48 * 60 {
        format!("осталось {} ч {} мин", m / 60, m % 60)
    } else {
        format!("осталось {} дн", m / (24 * 60))
    }
}

impl eframe::App for PlannerApp {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        // Панель скрылась — незавершённые подтверждения сбрасываются.
        if !self.shared.open.load(Ordering::Relaxed) {
            self.confirm = None;
        }
        let t = now();
        let (active, done_today) = {
            let s = self.store.lock().unwrap();
            (s.active(), s.done_on(t.date()))
        };

        egui::Frame::new()
            .fill(BG)
            .stroke(Stroke::new(1.0, Color32::from_rgb(60, 60, 68)))
            .inner_margin(16)
            .show(ui, |ui| {
                self.header(ui, t);
                self.add_form(ui, t);

                let footer_h = 44.0;
                egui::ScrollArea::vertical()
                    .auto_shrink([false, false])
                    .max_height(ui.available_height() - footer_h)
                    .show(ui, |ui| {
                        ui.label(
                            RichText::new(format!("К выполнению — {}", active.len())).color(MUTED),
                        );
                        if active.is_empty() {
                            ui.label("Задач нет. Добавьте первую в поле выше.");
                        }
                        for task in &active {
                            self.task_row(ui, task, t);
                        }
                        if !done_today.is_empty() {
                            ui.add_space(6.0);
                            ui.label(
                                RichText::new(format!("Сделано сегодня — {}", done_today.len()))
                                    .color(MUTED),
                            );
                            for task in &done_today {
                                self.task_row(ui, task, t);
                            }
                        }
                    });
                ui.add_space(4.0);
                self.footer(ui, t);
            });

        // Часы и «осталось N мин» обновляются сами.
        ui.ctx().request_repaint_after(Duration::from_secs(1));
    }
}
