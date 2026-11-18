# SunderCore Watcher

Windows notification-area application for the existing Character Ledger export
pipeline. The one-file, windowed EXE bundles Python, Tk, pystray, Pillow, and the
safe snapshot parser/publisher. GitHub CLI remains an external dependency and
uses the owner's existing authentication. No token is entered into this app.

The tray provides status/settings, sync now, pause/resume, website/log access,
and exit. First launch discovers a single local save or asks the user to select
one. It never chooses between multiple accounts silently. Closing the status
window keeps the watcher running. A Windows named mutex prevents duplicate
instances. `--tray` starts without opening the status window, including when
configuration is missing; a second `--tray` launch exits silently. `--show`
explicitly opens status. The optional `start_minimized` setting also hides the
initial window. Automatic startup is configured per user through the Windows
Run key, pointing to the installed EXE with `--tray`; no scheduled task is used.

Version 1.4 adds **Analyze now with local AI**, analysis status, and a separate
pause control for the Ollama advisor. The model runs on this PC. Its validated
priorities feed Character Ledger 1.12 and the website's Local advisor view.
See [LOCAL_AI.md](LOCAL_AI.md) for the save/analyze/reload workflow, public
Forever data attribution, performance limits, and failure behavior.

The worker waits for a stable file, validates the capture before publishing,
merges remote characters with SHA conflict handling, and skips unchanged/stale
snapshots. Transient failures retry with backoff. Settings, the sanitized cache,
and bounded logs live in `%LOCALAPPDATA%/SunderCoreWatcher`. They are never bundled
or uploaded. GitHub subprocess windows are hidden.

## Build on Windows

From the repository root, create a dedicated build environment and install the
dependencies in `tray/requirements-build.txt`:

```powershell
python -m venv .venv-tray
.venv-tray/Scripts/python.exe -m pip install -r tray/requirements-build.txt
./tray/build.ps1 -Python "$PWD/.venv-tray/Scripts/python.exe"
```

The default EXE destination is the parent of this repository. Use `-Destination`
and `-BuildDirectory` to change the output and intermediate directories.

## Tests

```powershell
python -m unittest discover -s tools -p 'test_*.py'
python -m unittest discover -s tray -p 'test_*.py'
```

These cover capture validation/privacy, stale/conflicting updates, debounce,
pause/resume, retries, source-change races, and hidden credential-safe processes.
Tests use mock GitHub responses and do not publish fixture data.

## Community gold discussions (Watcher 1.3 / Ledger 1.11)

A separate worker checks Blizzard's public Forever category feed and four
material/profession gold searches. It runs on startup and then every six hours
while watching is active. **Refresh community** in the tray checks sooner;
**Pause watching** pauses both workers. Network failures leave the previous
check timestamp visible, retain usable links, and retry in an hour. A forum
timeout does not block character publication.

The worker downloads public metadata only. It sends no character data, account
paths or credentials to forums. It writes `CommunityGoldData.lua` in the same
Forever installation as the selected SavedVariables file. It never edits that
saved file or downloads executable addon code. Source URLs, dates, sizes and
text are validated; data is serialized into escaped Lua literals atomically.
Reload WoW's UI after a refresh to load the new data.

The bundled `community_catalog.json` contains attributed, manually reviewed
strategy summaries. Their review dates are separate from forum retrieval dates.
Reviewed ideas stop annotating recommendations after 14 days and stay visible
as older references. New discussion links are explicitly unreviewed; keyword
matching only identifies related subjects. Reddit references are included as
reviewed links; Reddit is not automatically refreshed. This is a limited public
source sample, not comprehensive forum monitoring or automatic AI research.

Starting values: six-hour refresh, 12 recent links, 14-day discussion/review
window and a two-day feed-staleness indicator. Validation: a clock-driven test
must suppress repeated downloads, exclude expired/future posts, preserve the
last successful check on failure, and stop writes on pause/source changes. For
usefulness, review the first week of links; narrow topic filters if noisy, and
shorten review windows when hotfixes make ideas stale sooner.
