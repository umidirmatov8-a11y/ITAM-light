//! Встраивает значок и сведения о версии в DayPlanner.exe.

fn main() {
    println!("cargo:rerun-if-changed=assets/icon.ico");
    let target_windows = std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows");
    // Ресурсы компилирует rc.exe из Windows SDK, поэтому — только при сборке на Windows.
    // Кросс-сборка с Linux остаётся рабочей, но без значка.
    if target_windows && cfg!(windows) {
        let mut res = winresource::WindowsResource::new();
        let icon = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("assets/icon.ico");
        res.set_icon(icon.to_str().expect("путь к значку"));
        res.set("ProductName", "DayPlanner");
        res.set("FileDescription", "DayPlanner — планировщик задач на день");
        res.compile().expect("не удалось встроить значок в exe");
    }
}
