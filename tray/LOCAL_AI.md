# Local Character Ledger advisor

Character Ledger 1.12 and SunderCore Watcher 1.4 add an optional local planner.
The installed `qwen3.5:9b` model is called only through 127.0.0.1:11434. There
are no cloud-model fallbacks, shell tools, gameplay actions or arbitrary URLs
selected by model output. System HTTP proxies are ignored for model requests.

## Use

Keep Ollama and SunderCore Watcher running. Click Update SunderCore in game.
After the file settles, the watcher builds an analysis in its own worker. The
status window and log report progress; Analyze now bypasses the normal delay.
Reload WoW after the analysis is ready, then open Browse > Local advisor.
Today may reorder eligible suggestions; explicit tracking is preserved.
The website receives the analysis on the next watcher sync, independently of
the next game reload. Pause local AI stops future analysis and discards the
result of an active request. Pause watching also pauses AI and community work.
Pause AI ranking in the addon leaves all original local planning available.

There is no need to download a new model on this PC. On another PC, install
Ollama from its official source and install `qwen3.5:9b` first. No setup command
is executed automatically. Local-only model selection does not change the
user's global Ollama cloud settings or other applications using Ollama.

## Data and confidence

The local SQLite index imports public JSON exports from
https://github.com/gBlaku/wow-forever-kb and preserves build/update metadata.
The upstream project derives item data from Forever client DB2 data via Wago,
quests/vendors from QuestieDB (GPLv3), and loot/hidden-item fallback data from
VMangos Classic (GPLv2). See the upstream documentation and respective terms.
Raw exports and the index stay local; the website publishes selected references
with attribution, never the database. This is a known-source library, not all
public Forever knowledge. Missing/new content remains unknown. Classic drop
rates are deliberately excluded from prompts; acquisition references retain
their fallback warning. Exact IDs retrieve relevant items and quest records.
This version uses structured lookup, not embedding search or model training.

Forum input currently consists of recent validated discussion titles from the
existing watcher cache. Titles are unreviewed leads, not verified strategy
claims. Full discussions and broad crawling are not implemented. Auction data
comes from the addon snapshot and is never described as a live market feed.

## Constraints and failure behavior

The model returns up to three existing eligible task IDs, allowed reason codes and
known evidence IDs. Validation rejects invented IDs, citations, duplicates,
truncated replies and prerequisite-only tasks. Actions, amounts and sources
come from the deterministic addon plan. Displayed reasons are built from fixed explanations and saved task facts. AI
priorities can still be wrong; they are labeled and reviewable. All public rendering escapes text and restricts
clickable source hosts. Generated Lua contains serialized data, not model code.

Plans bind to name/realm, level, zone, professions, equipped IDs, bag quantities,
and focus. The addon additionally checks current task action/status before
ranking; the watcher checks candidate fingerprints including prices in actions.
Old snapshots and analysis expire after at most one day. Changing snapshots,
pause, shutdown or source selection during inference discards its result.
Unavailable inference keeps ordinary planning functional. Failed data refresh
keeps the prior index with its original data date. Character publishing runs
on a different thread and does not wait for the model.

Starting limits: 120 seconds settling delay, daily knowledge refresh, three
AI suggestions, 8K context, 800 output tokens, four CPU threads while WoW is
running, GPU offload when WoW is closed, and unload after each request. The
600-second request timeout accommodates CPU inference. These are initial
operating limits, not performance guarantees. Check response latency and game
frame times before increasing inference workload. There is no game polling.

## Verification / design notes

Player goal: choose useful solo work without adding another planning burden.
Clarity: dated suggestions, reasons and source confidence; Motivation: existing
goals and material needs; Response: background worker, pause and local fallback;
Satisfaction: ready status plus existing task tracking feedback; Fit: existing
Blizzard Classic panels and Today / My Goals / Browse. No gameplay state change
or new sound is introduced. Assumption: exported eligibility is authoritative;
validate with both-profession, pin, urgent bag, group and stale-price fixtures.

Run the Python tray/tools suites, Lua local-AI/workflow/UI/performance fixtures,
and a real Ollama request. Check new-user empty state, unknown IDs, old snapshots,
changed character during inference, failed refresh, model unavailability,
both-profession priority and source rendering. Keep gameplay actions manual.

Runtime state lives in %LOCALAPPDATA%/SunderCoreWatcher:
forever.sqlite, local-ai-plans.json and local-ai-last.json. None belongs in Git.
The generated addon file is LocalAIData.lua. The existing startup entry still
starts the same watcher EXE with --tray.
