# SunderCore

A public, snapshot-based dashboard for the Sundercore roster: character progress, next steps, professions, inventory, farming goals, and recorded outings.

Repository: [orest3781/sundercore](https://github.com/orest3781/sundercore). GitHub Pages address after deployment: [orest3781.github.io/sundercore](https://orest3781.github.io/sundercore/). The published site is built from `site/`; a custom domain can be configured later.

Character Ledger 1.12 and Watcher 1.4 add a **local Ollama advisor**. Click Update SunderCore in game; the tray watcher analyzes the saved character and publishes selected priorities to Today and Browse > Local advisor. Reload the game after analysis is ready to load those priorities into the addon. See [local advisor setup, data coverage and limits](tray/LOCAL_AI.md) and the [Windows tray watcher](tray/README.md).

## What is public

The website and its published character data can be read by anyone. A hidden screen or unlisted link does not make a JSON file private. Character Ledger exports are sanitized before publication: raw item strings, player GUIDs, account identifiers, and local file paths should never be committed. The surname **Sundercore** is a display convention; the exported in-game character names remain unchanged.

Site management uses your GitHub account and repository permissions. The browser does not receive a GitHub token and cannot write directly to the repository. The local companion uses the authenticated GitHub CLI when you explicitly request publication. Keep credentials out of `site/`, JSON exports, and Git commits.

## Refresh character snapshots

1. Enable Character Ledger in WoW Forever and log into a character. Open profession windows to capture known recipes. Visit the bank if its contents should be represented.
2. Run `/charout save`, then `/reload` or log out. The game writes SavedVariables to disk at reload/logout; an external helper cannot read the addon's unsaved in-memory state.
3. Run the local companion from this repository to import that character, using the command below.
4. Repeat the save/reload/import sequence for each character you want to update. The SavedVariables JSON export describes the last exported character; the companion merges that snapshot into the roster and retains previously imported characters. Alternatively, keep the explicitly enabled watcher running while switching characters and saving each one.

The companion reads saved files; it does not play the game or capture live combat directly. Offline characters retain their last imported snapshot and timestamp.

For the Windows quick-launch workflow, run **Update SunderCore.cmd** from the downloaded project after saving in game. It imports and publishes once using your existing GitHub CLI login. **Watch SunderCore.cmd** explicitly starts continuous watching and publishing until you stop it. Both locate the installed game's SavedVariables file locally; if there are multiple accounts or the installation is elsewhere, they ask you to choose the source. Your local account folder and installation path are not part of the published character data. The watcher does not install a startup task or schedule.

The equivalent command-line options are below. They also let you refresh locally without publishing.

Local refresh only:

```powershell
$snapshotPath = "C:\Games\World of Warcraft\_forever_\WTF\Account\<account>\SavedVariables\CharacterLedger.lua"
python tools/update_roster.py --source $snapshotPath --once
```

Replace `<account>` and the game installation path with your own. A saved Character Ledger `.json` file also works; repeat `--source` to import multiple files. Local output goes to `site/data/characters.json`. The updater requires Python 3.10 or newer and no third-party Python packages.

Publishing also requires the [GitHub CLI](https://cli.github.com/), with access to this repository. Authenticate locally using `gh auth login` and verify with `gh auth status`.

Explicit one-time refresh and publication:

```powershell
python tools/update_roster.py --source $snapshotPath --once --publish --repo orest3781/sundercore
```

Explicit continuous watch and publication:

```powershell
python tools/update_roster.py --source $snapshotPath --watch --publish --repo orest3781/sundercore
```

Watch mode only runs while that command remains running; stop it with Ctrl+C. No scheduled task, Windows startup entry, or automatic startup behavior is enabled by default. Use `python tools/update_roster.py --help` for source-location and other supported options. Publication updates the repository's `site/data/characters.json`; newer snapshots win. At an equal snapshot timestamp, only a newer local analysis may be attached; character facts remain unchanged. Site deployment follows the repository's Pages configuration.

## Preview the site locally

```powershell
python -m http.server 8000 --directory site
```

Open `http://localhost:8000`. Publishing is separate from this local preview. GitHub Pages serves static files; deploy changes through the repository's Pages workflow/settings.

## How to read the dashboard

### Today, My Goals and Browse

The website follows Character Ledger's simpler journal layout:

- **Today** emphasizes one next action and shows up to three saved tasks initially. Additional saved Today tasks remain available in an expandable section. The saved focus, tracked objective and both primary professions provide context without a wall of tools.
- **My Goals** brings both professions, saved crafting projects, tracked gear and shared material targets together. It shows the next saved profession step where available.
- **Browse** groups the detailed tools into Adventure, Professions & gold, and Journal & reference. Armory, gear upgrades, camps, recipes, bags, activity and source details remain accessible here. Existing character links continue to work.

Each task has a primary action to review its next step. **More** contains the explanation, a local review checkmark and a related tool link. **More ideas** exposes Soon, Someday, and reminders dismissed or set aside in game. Gold opportunities come from the saved addon analysis; any price estimates retain the snapshot's limitations.

Website checkmarks mean **Reviewed on this device**, scoped to this browser, character and saved-plan day. They do not complete tasks in game. Focus, checklist size, pins, pauses and project order are managed in Character Ledger. The site accepts daily-plan versions 1, 2 and 3; snapshots without a supported plan show a labeled basic fallback. It does not present old session budgets as task-duration estimates.

Queue learned recipes in the addon. Projects reserve shared materials and distinguish bag stock, bank withdrawals, intermediate crafts and missing materials. Completion counts successful crafting casts recorded in game. Click **Update SunderCore** in the planner or compact HUD to save and reload; the running watcher publishes the snapshot. The website does not require a watcher update for this layout change.

### Character armories

Open **Armory** and choose a character to see all 19 equipment slots, item icons, rarity colors, and saved item details. Each character has a shareable link. Gear comes exclusively from the Character Ledger snapshot. Click **Update SunderCore** in the addon's compact HUD to save and reload; the running tray watcher then publishes the updated snapshot.

Character portraits come from Blizzard's public Forever armory. Every site publication checks for new artwork using `tools/refresh_armory.py`; no Blizzard login or API key is needed. The displayed portrait timestamp is separate from the gear snapshot, and a warning appears if the image's equipment differs. If Blizzard cannot provide an image, the page keeps its last verified portrait or shows a clearly labeled placeholder. Equipment remains usable while artwork is unavailable. Icons come from Blizzard or Wowhead's Forever item data.

The automatic artwork check currently verifies the US character name, Sundercore surname, race, and class before accepting a portrait. It does not generate a portrait or provide a rotatable 3D model. To refresh the optional artwork locally, run `python tools/refresh_armory.py` before previewing the site.

### Snapshot details

- **Snapshot age:** values are accurate to the displayed capture time. The site does not show live online status, live bag changes, or live combat.
- **Next steps:** suggestions come from the saved addon analysis. Their source, requirements, and status matter. A gear shortlist is not a promise that an item is immediately obtainable.
- **Bags:** general bag capacity excludes specialized reagent bags and the keyring. Bank contents are separate and may be stale or unrecorded; an unvisited bank is not an empty bank.
- **Checklist:** stock is reserved after queued crafting materials. Collection quotas count newly received loot during an unpaused outing. A withdrawal or intermediate-craft task can still have additional materials missing.
- **Professions:** ranks are captured with the snapshot; recipe lists reflect the last profession scan. An empty recipe list can mean no scan was made.
- **Grinding:** camp scores reflect level, material, and quest relevance. They do not prove a camp has the highest XP/hour. Community sightings are not guaranteed spawn coordinates.
- **Activity:** recorded sessions are optional. Older exports may not support them. No sessions means no recorded sessions, not no playtime. Total session XP includes quests and rested XP; time includes travel and downtime, excluding explicit pauses.
- **Loot:** observed drops are distinct from received items. Normal corpse loot, skinning, pickpocketing, unknown, and legacy samples must remain separate. Missing data means unknown, not a zero drop chance.
- **Gear:** exported item levels, quality, requirements, and durability are shown where present. Version 1.5 adds candidate stat comparisons and estimated weighted scores. The public armory item details still omit raw item strings, talent builds, and auction prices. A default advice profile is not a confirmed specialization.

## Data sources and credit

Character data comes from local Character Ledger snapshots. Progression suggestions identify their Naowh Forever source in the export. Classic-derived starter camps remain labeled as such.

Community observations used by Character Ledger come from [Everloot](https://everloot.app). **Data from Everloot (https://everloot.app), CC BY-SA 4.0.** Any included derived community-data pack retains its source date, attribution, and [CC BY-SA 4.0 license](https://creativecommons.org/licenses/by-sa/4.0/). Its reported frequencies describe inspected loot windows and sample coverage, not complete server loot tables or guaranteed outcomes. See [Everloot's addon-author documentation](https://everloot.app/docs/addon-authors).

The source snapshots can differ in addon version even when both use `schemaVersion: 1`. Optional features are rendered only when captured; the site does not fill gaps with invented character statistics.


### Gear upgrade planner (Character Ledger 1.5 / Watcher 1.2)

The addon compares equipped items with its installed Naowh catalogue, learned crafts, trade-camp recipe unlocks, and carried gear. `/chargear` shows gains and losses, source locations, requirements, and materials. Paired slots and two-hand displacement are handled explicitly; unknown stats remain unknown. Scores use the selected profile and are estimates, not simulated DPS.

One eligible solo gear target joins Today. Dungeon goals stay in Soon. Queue a craft to use the existing material reservations and farm recommendations. Track, skip, profile selection and automatic-goal preferences are managed in game. The website's **Gear upgrades** tab displays the saved comparison and links from Today and Armory.

Merchant's Favor balance is read from the client. Recipe costs come from Naowh's observed vendor prices; unknown costs require a vendor visit. The planner shows profession gates, costs and deficits, while current reputation/access/stock must be checked at the vendor. It does not infer fixed crate payouts or purchase anything.

The export allowlist includes computed comparisons and currency balance, never raw saved variables, private account settings, item strings or the complete private catalogue. Existing characters without `gearPlan` remain supported and prompt for a fresh snapshot.
