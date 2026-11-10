//! Задачи и их хранение на диске (JSON в %APPDATA%\DayPlanner).

use chrono::{Duration, NaiveDate, NaiveDateTime};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

/// Сколько дней хранить выполненные и удалённые задачи после того, как они попали в отчёт.
const KEEP_DAYS: i64 = 30;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct Task {
    pub id: u64,
    pub title: String,
    /// Срок исполнения (дата и время).
    pub due: NaiveDateTime,
    pub created: NaiveDateTime,
    #[serde(default)]
    pub done_at: Option<NaiveDateTime>,
    #[serde(default)]
    pub deleted_at: Option<NaiveDateTime>,
}

impl Task {
    pub fn is_active(&self) -> bool {
        self.done_at.is_none() && self.deleted_at.is_none()
    }
}

#[derive(Default, Debug, Serialize, Deserialize)]
pub struct Store {
    #[serde(default)]
    pub tasks: Vec<Task>,
    #[serde(default)]
    pub next_id: u64,
    /// Последний день, за который отчёт уже записан.
    #[serde(default)]
    pub last_report: Option<NaiveDate>,
    #[serde(skip)]
    path: Option<PathBuf>,
}

impl Store {
    /// Читает файл; если его нет — пустое хранилище. Повреждённый файл сохраняется рядом как `.bad`.
    pub fn load(path: &Path) -> Store {
        let mut store = match std::fs::read_to_string(path) {
            Ok(text) => serde_json::from_str::<Store>(&text).unwrap_or_else(|_| {
                let _ = std::fs::copy(path, path.with_extension("json.bad"));
                Store::default()
            }),
            Err(_) => Store::default(),
        };
        store.path = Some(path.to_path_buf());
        store
    }

    /// Атомарная запись: во временный файл, затем переименование.
    pub fn save(&self) -> std::io::Result<()> {
        let Some(path) = &self.path else {
            return Ok(());
        };
        if let Some(dir) = path.parent() {
            std::fs::create_dir_all(dir)?;
        }
        let tmp = path.with_extension("json.tmp");
        std::fs::write(
            &tmp,
            serde_json::to_string_pretty(self).map_err(std::io::Error::other)?,
        )?;
        std::fs::rename(&tmp, path)
    }

    pub fn add(&mut self, title: &str, due: NaiveDateTime, now: NaiveDateTime) -> Option<u64> {
        let title = title.trim();
        if title.is_empty() {
            return None;
        }
        self.next_id += 1;
        self.tasks.push(Task {
            id: self.next_id,
            title: title.to_string(),
            due,
            created: now,
            done_at: None,
            deleted_at: None,
        });
        Some(self.next_id)
    }

    pub fn mark_done(&mut self, id: u64, now: NaiveDateTime) {
        if let Some(t) = self.tasks.iter_mut().find(|t| t.id == id && t.is_active()) {
            t.done_at = Some(now);
        }
    }

    /// Удаление «мягкое»: задача остаётся в файле, чтобы попасть в отчёт за день.
    pub fn delete(&mut self, id: u64, now: NaiveDateTime) {
        if let Some(t) = self
            .tasks
            .iter_mut()
            .find(|t| t.id == id && t.deleted_at.is_none())
        {
            t.deleted_at = Some(now);
        }
    }

    /// Активные задачи, ближайший срок — первым.
    pub fn active(&self) -> Vec<Task> {
        let mut v: Vec<Task> = self
            .tasks
            .iter()
            .filter(|t| t.is_active())
            .cloned()
            .collect();
        v.sort_by_key(|t| (t.due, t.id));
        v
    }

    /// Выполненные в указанный день (и не удалённые).
    pub fn done_on(&self, day: NaiveDate) -> Vec<Task> {
        let mut v: Vec<Task> = self
            .tasks
            .iter()
            .filter(|t| t.deleted_at.is_none() && t.done_at.is_some_and(|d| d.date() == day))
            .cloned()
            .collect();
        v.sort_by_key(|t| t.done_at);
        v
    }

    /// Была ли в этот день какая-то работа с задачами.
    pub fn has_activity(&self, day: NaiveDate) -> bool {
        self.tasks.iter().any(|t| {
            t.created.date() == day
                || t.done_at.is_some_and(|d| d.date() == day)
                || t.deleted_at.is_some_and(|d| d.date() == day)
        })
    }

    /// Прошедшие дни, за которые отчёт ещё не записан (программа была закрыта в полночь и т.п.).
    pub fn unreported_days(&self, today: NaiveDate) -> Vec<NaiveDate> {
        let first_activity = self.tasks.iter().map(|t| t.created.date()).min();
        let start = match (self.last_report, first_activity) {
            (Some(last), _) => last + Duration::days(1),
            (None, Some(first)) => first,
            (None, None) => return Vec::new(),
        };
        let mut days = Vec::new();
        let mut d = start;
        while d < today {
            if self.has_activity(d) {
                days.push(d);
            }
            d += Duration::days(1);
        }
        days
    }

    /// Убирает давно закрытые задачи, уже попавшие в отчёты.
    pub fn prune(&mut self, today: NaiveDate) {
        let Some(reported) = self.last_report else {
            return;
        };
        let limit = today - Duration::days(KEEP_DAYS);
        self.tasks.retain(|t| {
            let closed = match (t.done_at, t.deleted_at) {
                (Some(a), Some(b)) => Some(a.max(b)),
                (a, b) => a.or(b),
            };
            !closed.is_some_and(|c| c.date() < limit && c.date() <= reported)
        });
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

    #[test]
    fn add_done_delete() {
        let mut s = Store::default();
        assert_eq!(s.add("   ", dt(10, 12, 0), dt(10, 9, 0)), None);
        let a = s.add(" Позвонить ", dt(10, 18, 0), dt(10, 9, 0)).unwrap();
        let b = s.add("Отчёт", dt(10, 12, 0), dt(10, 9, 5)).unwrap();
        assert_eq!(
            s.active().iter().map(|t| t.id).collect::<Vec<_>>(),
            vec![b, a]
        );
        assert_eq!(s.active()[1].title, "Позвонить");

        s.mark_done(b, dt(10, 11, 0));
        s.mark_done(b, dt(10, 11, 30)); // повторно — без эффекта
        assert_eq!(s.done_on(day(10))[0].done_at, Some(dt(10, 11, 0)));
        s.delete(a, dt(10, 13, 0));
        assert!(s.active().is_empty());
        assert_eq!(s.tasks.len(), 2, "удалённая задача остаётся для отчёта");
    }

    #[test]
    fn unreported_days_only_with_activity() {
        let mut s = Store::default();
        assert!(s.unreported_days(day(10)).is_empty());
        let a = s.add("A", dt(8, 12, 0), dt(5, 9, 0)).unwrap();
        s.mark_done(a, dt(7, 10, 0));
        assert_eq!(s.unreported_days(day(10)), vec![day(5), day(7)]);
        s.last_report = Some(day(5));
        assert_eq!(s.unreported_days(day(10)), vec![day(7)]);
        s.last_report = Some(day(9));
        assert!(s.unreported_days(day(10)).is_empty());
    }

    #[test]
    fn save_load_roundtrip_and_prune() {
        let dir = std::env::temp_dir().join(format!("dayplanner-test-{}", std::process::id()));
        let path = dir.join("sub").join("tasks.json");
        let mut s = Store::load(&path);
        let a = s.add("Старая", dt(1, 12, 0), dt(1, 9, 0)).unwrap();
        s.add("Живая", dt(1, 12, 0), dt(1, 9, 0)).unwrap();
        s.mark_done(a, dt(1, 10, 0));
        s.last_report = Some(day(1));
        s.save().unwrap();

        let mut loaded = Store::load(&path);
        assert_eq!(loaded.tasks, s.tasks);
        assert_eq!(loaded.next_id, 2);
        loaded.prune(NaiveDate::from_ymd_opt(2027, 1, 15).unwrap());
        assert_eq!(
            loaded.tasks.len(),
            1,
            "активные задачи не удаляются никогда"
        );
        assert_eq!(loaded.tasks[0].title, "Живая");
        let _ = std::fs::remove_dir_all(dir);
    }
}
