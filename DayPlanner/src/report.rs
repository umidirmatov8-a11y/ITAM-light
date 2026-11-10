//! Ежедневный отчёт о проделанной работе: C:\worksheet\Отчет_ГГГГ-ММ-ДД.txt

use crate::model::{Store, Task};
use chrono::{NaiveDate, NaiveDateTime};
use std::fmt::Write as _;
use std::path::{Path, PathBuf};

/// Время, после которого отчёт за текущий день пишется автоматически.
pub const END_OF_DAY: (u32, u32) = (23, 59);

/// Папка отчётов. Переменная DAYPLANNER_REPORT_DIR переопределяет её (нужно для проверки).
pub fn report_dir() -> PathBuf {
    if let Some(dir) = std::env::var_os("DAYPLANNER_REPORT_DIR") {
        return PathBuf::from(dir);
    }
    if cfg!(windows) {
        PathBuf::from(r"C:\worksheet")
    } else {
        PathBuf::from("worksheet")
    }
}

/// Дата в имени файла — отчёты разных дней не перекрывают друг друга.
pub fn file_name(day: NaiveDate) -> String {
    format!("Отчет_{}.txt", day.format("%Y-%m-%d"))
}

const WEEKDAYS: [&str; 7] = [
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
];

pub fn weekday_ru(day: NaiveDate) -> &'static str {
    use chrono::Datelike;
    WEEKDAYS[day.weekday().num_days_from_monday() as usize]
}

fn fmt_dt(dt: NaiveDateTime) -> String {
    dt.format("%d.%m.%Y %H:%M").to_string()
}

pub fn build(store: &Store, day: NaiveDate, generated: NaiveDateTime) -> String {
    let end = day.and_hms_opt(23, 59, 59).unwrap();
    let on_day = |dt: Option<NaiveDateTime>| dt.is_some_and(|d| d.date() == day);

    let mut done: Vec<&Task> = store.tasks.iter().filter(|t| on_day(t.done_at)).collect();
    done.sort_by_key(|t| t.done_at);
    let mut added: Vec<&Task> = store
        .tasks
        .iter()
        .filter(|t| t.created.date() == day)
        .collect();
    added.sort_by_key(|t| t.created);
    let mut deleted: Vec<&Task> = store
        .tasks
        .iter()
        .filter(|t| on_day(t.deleted_at))
        .collect();
    deleted.sort_by_key(|t| t.deleted_at);
    // Остались невыполненными на конец дня.
    let mut open: Vec<&Task> = store
        .tasks
        .iter()
        .filter(|t| {
            t.created <= end
                && !t.done_at.is_some_and(|d| d <= end)
                && !t.deleted_at.is_some_and(|d| d <= end)
        })
        .collect();
    open.sort_by_key(|t| t.due);
    // Отчёт, сформированный вручную среди дня, считает просрочку на текущий момент.
    let cutoff = generated.min(end);
    let overdue = open.iter().filter(|t| t.due <= cutoff).count();
    let in_time = done.iter().filter(|t| t.done_at.unwrap() <= t.due).count();

    let mut s = String::new();
    let line = "=".repeat(60);
    let _ = writeln!(s, "{line}");
    let _ = writeln!(s, "ОТЧЁТ О ПРОДЕЛАННОЙ РАБОТЕ");
    let _ = writeln!(s, "Дата: {} ({})", day.format("%d.%m.%Y"), weekday_ru(day));
    let _ = writeln!(s, "Сформирован: {}", fmt_dt(generated));
    let _ = writeln!(s, "{line}");

    let _ = writeln!(s, "\nВЫПОЛНЕНО ({})", done.len());
    for (i, t) in done.iter().enumerate() {
        let at = t.done_at.unwrap();
        let mark = if at <= t.due {
            "в срок"
        } else {
            "с опозданием"
        };
        let _ = writeln!(s, "  {}. {}", i + 1, t.title);
        let _ = writeln!(
            s,
            "     срок: {} | выполнено: {} | {mark}",
            fmt_dt(t.due),
            at.format("%H:%M")
        );
    }
    if done.is_empty() {
        let _ = writeln!(s, "  —");
    }

    let (eh, em) = END_OF_DAY;
    let midday = generated < day.and_hms_opt(eh, em, 0).unwrap();
    let when = if midday {
        "НА МОМЕНТ ОТЧЁТА"
    } else {
        "НА КОНЕЦ ДНЯ"
    };
    let _ = writeln!(s, "\nНЕ ВЫПОЛНЕНО {when} ({})", open.len());
    for (i, t) in open.iter().enumerate() {
        let mark = if t.due <= cutoff {
            " | ПРОСРОЧЕНО"
        } else {
            ""
        };
        let _ = writeln!(s, "  {}. {}", i + 1, t.title);
        let _ = writeln!(s, "     срок: {}{mark}", fmt_dt(t.due));
    }
    if open.is_empty() {
        let _ = writeln!(s, "  —");
    }

    let _ = writeln!(s, "\nДОБАВЛЕНО ЗА ДЕНЬ ({})", added.len());
    for (i, t) in added.iter().enumerate() {
        let _ = writeln!(
            s,
            "  {}. {} (в {}, срок: {})",
            i + 1,
            t.title,
            t.created.format("%H:%M"),
            fmt_dt(t.due)
        );
    }
    if added.is_empty() {
        let _ = writeln!(s, "  —");
    }

    let _ = writeln!(s, "\nУДАЛЕНО ЗА ДЕНЬ ({})", deleted.len());
    for (i, t) in deleted.iter().enumerate() {
        let state = if t.done_at.is_some() {
            "была выполнена"
        } else {
            "без выполнения"
        };
        let _ = writeln!(
            s,
            "  {}. {} (в {}, {state})",
            i + 1,
            t.title,
            t.deleted_at.unwrap().format("%H:%M")
        );
    }
    if deleted.is_empty() {
        let _ = writeln!(s, "  —");
    }

    let _ = writeln!(s, "\n{line}");
    let _ = writeln!(
        s,
        "ИТОГО: выполнено {} (в срок {}, с опозданием {}), не выполнено {} (просрочено {}),",
        done.len(),
        in_time,
        done.len() - in_time,
        open.len(),
        overdue
    );
    let _ = writeln!(
        s,
        "       добавлено {}, удалено {}",
        added.len(),
        deleted.len()
    );
    let _ = writeln!(s, "{line}");
    s
}

/// Пишет отчёт за день; папка создаётся, если её нет. Возвращает путь к файлу.
pub fn write(
    store: &Store,
    day: NaiveDate,
    generated: NaiveDateTime,
    dir: &Path,
) -> std::io::Result<PathBuf> {
    std::fs::create_dir_all(dir)?;
    let path = dir.join(file_name(day));
    // BOM — чтобы Блокнот любой версии Windows открыл кириллицу правильно.
    let text = format!(
        "\u{feff}{}",
        build(store, day, generated).replace('\n', "\r\n")
    );
    std::fs::write(&path, text)?;
    Ok(path)
}

/// Плановая работа с отчётами: догоняет пропущенные дни и пишет отчёт в конце дня.
/// Возвращает true, если хранилище изменилось и его нужно сохранить.
pub fn run_schedule(store: &mut Store, now: NaiveDateTime, dir: &Path) -> bool {
    let today = now.date();
    let mut changed = false;
    for day in store.unreported_days(today) {
        if write(store, day, now, dir).is_err() {
            return changed; // папка недоступна — повторим на следующем тике
        }
        store.last_report = Some(day);
        changed = true;
    }
    let (h, m) = END_OF_DAY;
    let end_reached = now.time() >= chrono::NaiveTime::from_hms_opt(h, m, 0).unwrap();
    if end_reached && store.last_report != Some(today) && write(store, today, now, dir).is_ok() {
        store.last_report = Some(today);
        store.prune(today);
        changed = true;
    }
    changed
}

/// После изменения задач: если отчёт за сегодня уже записан (после 23:59) — обновить его.
pub fn refresh_if_reported(store: &Store, now: NaiveDateTime, dir: &Path) {
    if store.last_report == Some(now.date()) {
        let _ = write(store, now.date(), now, dir);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn dt(d: u32, h: u32, m: u32) -> NaiveDateTime {
        NaiveDate::from_ymd_opt(2026, 11, d)
            .unwrap()
            .and_hms_opt(h, m, 0)
            .unwrap()
    }
    fn day(d: u32) -> NaiveDate {
        NaiveDate::from_ymd_opt(2026, 11, d).unwrap()
    }
    fn tmp(name: &str) -> PathBuf {
        std::env::temp_dir().join(format!("dayplanner-{name}-{}", std::process::id()))
    }

    fn sample() -> Store {
        let mut s = Store::default();
        let a = s.add("Сдать отчёт", dt(10, 12, 0), dt(10, 9, 0)).unwrap();
        let b = s
            .add("Позвонить клиенту", dt(10, 10, 0), dt(10, 9, 1))
            .unwrap();
        let c = s.add("Лишняя", dt(10, 15, 0), dt(10, 9, 2)).unwrap();
        s.add("Просроченная", dt(10, 16, 0), dt(9, 9, 0)).unwrap();
        s.add("На завтра", dt(11, 16, 0), dt(10, 9, 3)).unwrap();
        s.mark_done(a, dt(10, 11, 30));
        s.mark_done(b, dt(10, 14, 0));
        s.delete(c, dt(10, 15, 30));
        s
    }

    #[test]
    fn report_contents() {
        let r = build(&sample(), day(10), dt(10, 23, 59));
        assert!(r.contains("Дата: 10.11.2026 (вторник)"));
        assert!(r.contains("ВЫПОЛНЕНО (2)"));
        assert!(r.contains("срок: 10.11.2026 12:00 | выполнено: 11:30 | в срок"));
        assert!(r.contains("срок: 10.11.2026 10:00 | выполнено: 14:00 | с опозданием"));
        assert!(r.contains("НЕ ВЫПОЛНЕНО НА КОНЕЦ ДНЯ (2)"));
        assert!(r.contains("срок: 10.11.2026 16:00 | ПРОСРОЧЕНО"));
        assert!(r.contains("срок: 11.11.2026 16:00\n"));
        assert!(r.contains("ДОБАВЛЕНО ЗА ДЕНЬ (4)"));
        assert!(r.contains("УДАЛЕНО ЗА ДЕНЬ (1)"));
        assert!(r.contains("выполнено 2 (в срок 1, с опозданием 1), не выполнено 2 (просрочено 1)"));
    }

    #[test]
    fn midday_report_is_not_overdue_yet() {
        let r = build(&sample(), day(10), dt(10, 15, 45));
        assert!(r.contains("НЕ ВЫПОЛНЕНО НА МОМЕНТ ОТЧЁТА (2)"));
        assert!(r.contains("срок: 10.11.2026 16:00\n"));
        assert!(r.contains("(просрочено 0)"));
    }

    #[test]
    fn report_of_past_day_ignores_later_events() {
        // Задача выполнена 10-го: в отчёте за 9-е она ещё «не выполнена».
        let r = build(&sample(), day(9), dt(10, 8, 0));
        assert!(r.contains("ВЫПОЛНЕНО (0)"));
        assert!(r.contains("НЕ ВЫПОЛНЕНО НА КОНЕЦ ДНЯ (1)"));
        assert!(r.contains("Просроченная"));
        assert!(!r.contains("Сдать отчёт"));
    }

    #[test]
    fn creates_folder_and_dated_files() {
        let dir = tmp("report").join("worksheet");
        assert!(!dir.exists());
        let s = sample();
        let p1 = write(&s, day(10), dt(10, 23, 59), &dir).unwrap();
        let p2 = write(&s, day(11), dt(11, 23, 59), &dir).unwrap();
        assert_eq!(
            p1.file_name().unwrap().to_str().unwrap(),
            "Отчет_2026-11-10.txt"
        );
        assert_ne!(p1, p2);
        assert!(p1.exists() && p2.exists());
        let bytes = std::fs::read(&p1).unwrap();
        assert_eq!(&bytes[..3], &[0xEF, 0xBB, 0xBF]);
        let _ = std::fs::remove_dir_all(dir.parent().unwrap());
    }

    #[test]
    fn schedule_end_of_day_and_catch_up() {
        let dir = tmp("schedule");
        let mut s = sample();

        // Днём 10-го: догоняем только 9-е (там была активность), отчёта за сегодня ещё нет.
        assert!(run_schedule(&mut s, dt(10, 15, 0), &dir));
        assert!(dir.join(file_name(day(9))).exists());
        assert!(!dir.join(file_name(day(10))).exists());
        assert!(!run_schedule(&mut s, dt(10, 15, 1), &dir));

        // 23:59 — отчёт за сегодня, один раз.
        assert!(run_schedule(&mut s, dt(10, 23, 59), &dir));
        assert!(dir.join(file_name(day(10))).exists());
        assert_eq!(s.last_report, Some(day(10)));
        assert!(!run_schedule(&mut s, dt(10, 23, 59), &dir));

        // Программа была выключена в полночь 11-го: 12-го отчёт за 11-е дописывается.
        let id = s.add("Поздняя", dt(11, 20, 0), dt(11, 10, 0)).unwrap();
        s.mark_done(id, dt(11, 19, 0));
        assert!(run_schedule(&mut s, dt(12, 8, 0), &dir));
        let text = std::fs::read_to_string(dir.join(file_name(day(11)))).unwrap();
        assert!(text.contains("Поздняя"));
        // Отчёт за 10-е не тронут.
        let old = std::fs::read_to_string(dir.join(file_name(day(10)))).unwrap();
        assert!(!old.contains("Поздняя"));
        let _ = std::fs::remove_dir_all(dir);
    }
}
