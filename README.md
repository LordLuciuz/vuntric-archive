# Vûntric Linguistic Archive

This is the **application source code**, not the user's linguistic database. The archive itself runs locally with Python, Streamlit and SQLite. No ChatGPT or GitHub subscription is required to run it.

## Initial repository setup

1. Create a **public**, empty repository named `vuntric-archive` on GitHub. Keep its default branch `main`.
2. Extract the supplied *repository source* ZIP into a temporary folder. Upload **only these extracted source files and folders** through **Add file → Upload files** in GitHub; preserve the `.github/workflows` and `tools` paths.
3. Commit the files to `main`. The workflow **Publish Vuntric Archive update** should create a release tagged `v0.1.2` with an attached `VuntricArchive_Update_0.1.2.zip`.
4. If the workflow is disabled or fails, check **Actions** and the repository's Actions permissions.
5. Configure the installed updater on Windows with the repository's public GitHub URL.

## Publishing future updates

- Edit the application source files as necessary.
- **Increment `VERSION`** (`0.1.2` → `0.1.3`, etc.) in the same commit as those changes.
- The GitHub Actions workflow packages `app.py`, `storage.py`, `archive_updater.py`, `requirements.txt`, and optional `modules/*.py` and publishes a new Release automatically when you push changes to `main`.
- On Windows, stop the archive and double-click `Update Archive.bat`. It checks the latest Release, verifies its SHA-256 digest, previews changes, backs up the old code, and applies the release after explicit approval.
- The downloaded package is strictly limited to application code; language-data imports remain a separate feature inside the app.

For manual packaging: `python tools/build_release.py 0.1.3` (after setting VERSION to that version).

## Do not publish personal data

**Never upload the local `Archive` installation folder.** The `data/` directory (including `.sqlite3` databases), `.venv/`, backups, exports, local PDF documents, and update configuration belong exclusively on the user's PC. The `.gitignore` file helps exclude them when using Git but does not protect against manual browser uploads.

GitHub Releases are public in this setup. The updater uses the public release API without requiring a local token. It does not automatically install new Python dependencies; if `requirements.txt` changes, install those dependencies into the local `.venv` separately.
