//! Логика «горячего» верхнего края экрана и анимация выезда панели.
//! Чистые функции без Win32 — проверяются тестами.

/// Сколько мс курсор должен пробыть у края, прежде чем панель откроется.
pub const DWELL_MS: u64 = 160;
/// Сколько мс курсор должен пробыть вне панели, прежде чем она скроется.
pub const LEAVE_MS: u64 = 350;
/// Длительность выезда/скрытия.
pub const ANIM_MS: f32 = 340.0;
/// Запас вокруг панели, в пределах которого курсор считается «на панели».
const MARGIN: i32 = 14;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Rect {
    pub left: i32,
    pub top: i32,
    pub right: i32,
    pub bottom: i32,
}

impl Rect {
    pub fn contains(&self, x: i32, y: i32) -> bool {
        x >= self.left && x < self.right && y >= self.top && y < self.bottom
    }
    pub fn width(&self) -> i32 {
        self.right - self.left
    }
    pub fn height(&self) -> i32 {
        self.bottom - self.top
    }
}

pub struct Input {
    pub now_ms: u64,
    pub cursor: (i32, i32),
    /// Зажата ли левая кнопка мыши (перетаскивание окна, выделение и т.п.).
    pub lmb: bool,
    /// Экран, у верхнего края которого живёт панель.
    pub screen: Rect,
    /// Видимая сейчас часть панели на экране.
    pub panel: Rect,
    /// Панель закреплена — не скрывать.
    pub pinned: bool,
}

#[derive(Default)]
pub struct Trigger {
    open: bool,
    /// Край «заблокирован»: кнопка была зажата у края (тащат окно). Снимается,
    /// когда курсор ушёл от края с отпущенной кнопкой.
    blocked: bool,
    edge_since: Option<u64>,
    away_since: Option<u64>,
}

impl Trigger {
    /// Возвращает, должна ли панель быть открыта.
    pub fn update(&mut self, i: &Input) -> bool {
        let (x, y) = i.cursor;
        let at_edge = y <= i.screen.top && x >= i.screen.left && x < i.screen.right;

        if !self.open {
            if at_edge && i.lmb {
                // Окно перетаскивают к верхнему краю — не открываемся ни сейчас,
                // ни сразу после отпускания кнопки.
                self.blocked = true;
            } else if !at_edge && !i.lmb {
                self.blocked = false;
            }
            if at_edge && !i.lmb && !self.blocked {
                let since = *self.edge_since.get_or_insert(i.now_ms);
                if i.now_ms.saturating_sub(since) >= DWELL_MS {
                    self.open = true;
                    self.edge_since = None;
                    self.away_since = None;
                }
            } else {
                self.edge_since = None;
            }
        } else {
            let near = Rect {
                left: i.panel.left - MARGIN,
                top: i.screen.top - 10_000,
                right: i.panel.right + MARGIN,
                bottom: i.panel.bottom + MARGIN,
            };
            // Зажатая кнопка (выделение текста, протяжка значения) панель не закрывает.
            if near.contains(x, y) || i.lmb || i.pinned {
                self.away_since = None;
            } else {
                let since = *self.away_since.get_or_insert(i.now_ms);
                if i.now_ms.saturating_sub(since) >= LEAVE_MS {
                    self.open = false;
                    self.away_since = None;
                }
            }
        }
        self.open
    }
}

/// Анимация как у панелей macOS: быстрый старт с плавным торможением при выезде
/// и плавный разгон при скрытии. При смене направления на полпути положение не скачет.
pub struct Slide {
    t: f32,
    opening: bool,
}

impl Default for Slide {
    fn default() -> Self {
        Slide {
            t: 0.0,
            opening: false,
        }
    }
}

impl Slide {
    /// Сдвигает анимацию на `dt_ms` и возвращает долю выезда 0.0 (скрыта) ..= 1.0 (открыта).
    pub fn step(&mut self, open: bool, dt_ms: f32) -> f32 {
        if open != self.opening {
            let p = self.position();
            self.opening = open;
            // Подбираем t так, чтобы новая кривая проходила через текущее положение.
            self.t = if open {
                1.0 - (1.0 - p).powf(0.25)
            } else {
                p.powf(1.0 / 3.0)
            };
        }
        let d = dt_ms / ANIM_MS;
        self.t = if open {
            (self.t + d).min(1.0)
        } else {
            (self.t - d).max(0.0)
        };
        self.position()
    }

    pub fn position(&self) -> f32 {
        if self.opening {
            1.0 - (1.0 - self.t).powi(4) // ease-out quart
        } else {
            self.t.powi(3) // при убывании t: плавный разгон к краю
        }
    }

    pub fn is_moving(&self) -> bool {
        if self.opening {
            self.t < 1.0
        } else {
            self.t > 0.0
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SCREEN: Rect = Rect {
        left: 0,
        top: 0,
        right: 1920,
        bottom: 1080,
    };
    const PANEL: Rect = Rect {
        left: 580,
        top: 0,
        right: 1340,
        bottom: 560,
    };

    fn inp(now_ms: u64, cursor: (i32, i32), lmb: bool) -> Input {
        Input {
            now_ms,
            cursor,
            lmb,
            screen: SCREEN,
            panel: PANEL,
            pinned: false,
        }
    }

    #[test]
    fn opens_after_dwell_at_top_edge() {
        let mut t = Trigger::default();
        assert!(!t.update(&inp(0, (900, 300), false)));
        assert!(!t.update(&inp(10, (900, 0), false)));
        assert!(!t.update(&inp(100, (900, 0), false)), "ещё не выждали");
        assert!(t.update(&inp(10 + DWELL_MS, (900, 0), false)));
    }

    #[test]
    fn quick_touch_of_edge_does_not_open() {
        let mut t = Trigger::default();
        t.update(&inp(0, (900, 0), false));
        t.update(&inp(50, (900, 40), false));
        assert!(
            !t.update(&inp(400, (900, 0), false)),
            "отсчёт начался заново"
        );
    }

    #[test]
    fn dragging_window_to_top_does_not_open() {
        let mut t = Trigger::default();
        // Схватили заголовок окна и тащим вверх.
        t.update(&inp(0, (900, 300), true));
        for ms in (10..2000).step_by(10) {
            assert!(!t.update(&inp(ms, (900, 0), true)));
        }
        // Отпустили у края (окно развернулось) и держим курсор там же — всё равно закрыто.
        for ms in (2000..4000).step_by(10) {
            assert!(!t.update(&inp(ms, (900, 0), false)));
        }
        // Увели курсор вниз и вернулись — теперь открывается.
        t.update(&inp(4000, (900, 200), false));
        t.update(&inp(4010, (900, 0), false));
        assert!(t.update(&inp(4010 + DWELL_MS, (900, 0), false)));
    }

    #[test]
    fn press_during_dwell_cancels() {
        let mut t = Trigger::default();
        t.update(&inp(0, (900, 0), false));
        t.update(&inp(50, (900, 0), true)); // нажали на заголовок развёрнутого окна
        assert!(!t.update(&inp(500, (900, 0), false)));
    }

    #[test]
    fn closes_after_leaving_panel() {
        let mut t = Trigger::default();
        t.update(&inp(0, (900, 0), false));
        assert!(t.update(&inp(DWELL_MS, (900, 0), false)));
        assert!(t.update(&inp(1000, (900, 400), false)), "курсор на панели");
        assert!(t.update(&inp(1100, (900, 800), false)), "ушёл, но ждём");
        assert!(
            t.update(&inp(1200, (900, 400), false)),
            "вернулся — отсчёт сброшен"
        );
        assert!(t.update(&inp(1300, (100, 800), false)));
        assert!(!t.update(&inp(1300 + LEAVE_MS, (100, 800), false)));
    }

    #[test]
    fn pinned_or_pressed_button_keeps_open() {
        let mut t = Trigger::default();
        t.update(&inp(0, (900, 0), false));
        t.update(&inp(DWELL_MS, (900, 0), false));
        let mut i = inp(1000, (100, 900), false);
        i.pinned = true;
        t.update(&i);
        i.now_ms = 5000;
        assert!(t.update(&i));
        assert!(t.update(&inp(6000, (100, 900), true)), "кнопка зажата");
        t.update(&inp(6001, (100, 900), false));
        assert!(!t.update(&inp(6001 + LEAVE_MS, (100, 900), false)));
    }

    #[test]
    fn slide_is_monotonic_and_reaches_ends() {
        let mut s = Slide::default();
        let mut prev = 0.0;
        for _ in 0..100 {
            let p = s.step(true, 8.0);
            assert!(p >= prev);
            prev = p;
        }
        assert_eq!(prev, 1.0);
        assert!(!s.is_moving());
        for _ in 0..100 {
            let p = s.step(false, 8.0);
            assert!(p <= prev);
            prev = p;
        }
        assert_eq!(prev, 0.0);
        assert!(!s.is_moving());
    }

    #[test]
    fn slide_reversal_has_no_jump() {
        let mut s = Slide::default();
        let mut p = 0.0;
        for _ in 0..12 {
            p = s.step(true, 8.0);
        }
        let back = s.step(false, 8.0);
        assert!((back - p).abs() < 0.08, "скачок {p} -> {back}");
        let fwd = s.step(true, 8.0);
        assert!((fwd - back).abs() < 0.08, "скачок {back} -> {fwd}");
    }
}
