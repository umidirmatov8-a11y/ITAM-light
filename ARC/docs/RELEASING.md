# Выпуск новой версии

Релиз на GitHub публикуется автоматически, когда в репозиторий отправлен тег `arc-vX.Y.Z`.

## Шаги

1. Поднимите версию в двух местах (должны совпадать):
   * `app/package.json` → `"version"` (и `npm install --package-lock-only` в `app/`, чтобы обновился lock-файл);
   * `backend/arc_backend/__init__.py` → `__version__`.
2. Добавьте раздел `## X.Y.Z — дата` в [CHANGELOG.md](../CHANGELOG.md) — его текст станет описанием релиза.
   Тест `tests/test_release.py` не даст забыть об этом.
3. Влейте изменения в `main` и дождитесь зелёного CI.
4. Поставьте тег на коммит в `main` и отправьте его:

   ```powershell
   git checkout main; git pull
   git tag arc-v1.0.0
   git push origin arc-v1.0.0
   ```

   Или на GitHub: Releases → «Draft a new release» → «Choose a tag» → `arc-v1.0.0` → цель `main` →
   **только создайте тег** (Publish не нужен — CI опубликует релиз сам).

## Что делает CI

Для тега запускаются все проверки (`build-test`, `signing`, `local-ai`). Только если все прошли, задание
`release`:

* проверяет, что тег, `package.json` и `__version__` называют одну версию и что в CHANGELOG есть раздел;
* берёт подписанный установщик (артефакт `ARC-Setup-signed`, если в секретах есть сертификат) или обычный;
* сверяет SHA-256 и публикует релиз `A.R.C. X.Y.Z` с файлами `ARC-Setup-X.Y.Z.exe` и `.sha256`;
* версии с суффиксом (`arc-v1.1.0-beta.1`) публикуются как pre-release.

Постоянная ссылка на последнюю версию:
`https://github.com/umidirmatov8-a11y/ITAM-light/releases/latest`.

Если задание упало (например, версии не совпали), исправьте, удалите тег (`git push --delete origin arc-vX.Y.Z`,
`git tag -d arc-vX.Y.Z`) и поставьте его заново на исправленный коммит.
