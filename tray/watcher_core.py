"""Tray-independent watcher. No game interaction and no credential storage."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone

import update_roster as roster

REPOSITORY = 'orest3781/sundercore'
WEBSITE = 'https://orest3781.github.io/sundercore/'
GAME_ROOT = Path('C:/Games/World of Warcraft/_forever_')


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def discover_sources(game_root=GAME_ROOT):
    return sorted(p for p in (game_root/'WTF'/'Account').glob('*/SavedVariables/CharacterLedger.lua') if p.is_file())


def find_gh():
    found = shutil.which('gh')
    if found:
        return found
    candidate = Path(os.environ.get('ProgramFiles', 'C:/Program Files'))/'GitHub CLI'/'gh.exe'
    return str(candidate) if candidate.is_file() else None


class HiddenGitHub:
    """Use gh's existing authentication; never echo API payloads or stderr."""
    def __init__(self, executable=None):
        self.executable = executable or find_gh()
        self.cancelled = threading.Event()
        self.lock = threading.Lock()
        self.process = None

    def __call__(self, endpoint, payload=None):
        if not self.executable:
            raise RuntimeError('GitHub CLI is missing. Install it from cli.github.com and sign in with gh auth login, then reopen this app.')
        if self.cancelled.is_set():
            raise RuntimeError('Watcher is exiting.')
        args = [self.executable, 'api', endpoint, '-H', 'Accept: application/vnd.github+json']
        if payload is not None:
            args += ['--method', 'PUT', '--input', '-']
        with self.lock:
            if self.cancelled.is_set():
                raise RuntimeError('Watcher is exiting.')
            proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True, encoding='utf-8',
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.process = proc
        try:
            try:
                stdout, stderr = proc.communicate(roster.encoded(payload) if payload is not None else None, timeout=35)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                raise RuntimeError('GitHub did not respond. The watcher will retry automatically.') from None
            if proc.returncode:
                match = re.search(r'HTTP\s+(\d{3})', stderr)
                raise roster.GitHubError(match.group(1) if match else None)
            return roster.strict_json(stdout)
        finally:
            with self.lock:
                if self.process is proc:
                    self.process = None

    def close(self):
        self.cancelled.set()
        with self.lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()


class Watcher:
    def __init__(self, source, data_dir, callback, api=None, clock=time.monotonic):
        self.source = Path(source) if source else None
        self.data_dir = Path(data_dir)
        self.callback = callback
        self.api = api or HiddenGitHub()
        self.clock = clock
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self.paused = False
        self.force = False
        self.last_success_signature = None
        self.pending_signature = None
        self.retry_at = 0
        self.failures = 0
        self.generation = 0
        self.state = dict(phase='Starting', detail='Looking for your addon save.', character='',
                          captured_at='', last_check='', last_publish='', paused=False)
        self._last_emitted = None

    def emit(self, phase, detail, **changes):
        with self.lock:
            self.state.update(changes)
            self.state.update(phase='Paused' if self.paused else phase, detail=detail, paused=self.paused)
            value = dict(self.state)
        if value != self._last_emitted:
            self._last_emitted = value
            self.callback(value)

    def set_source(self, source):
        with self.lock:
            self.source = Path(source)
            self.generation += 1
            self.last_success_signature = None
            self.pending_signature = None
            self.retry_at = 0
        self.emit('Watching', 'Save selected. Waiting for a stable snapshot.')
        self.wake.set()

    def set_paused(self, paused):
        with self.lock:
            self.paused = bool(paused)
            self.generation += 1
        self.emit('Watching', 'Watching is paused. An upload already in progress may finish.' if paused else 'Watching for saved snapshots.')
        self.wake.set()

    def sync_now(self):
        with self.lock:
            if self.paused:
                return
            self.force = True
        self.wake.set()

    def tick(self):
        with self.lock:
            if self.paused or self.stop_event.is_set():
                return
            source, generation = self.source, self.generation
            force, self.force = self.force, False
        if source is None:
            self.emit('Choose a save', 'Choose CharacterLedger.lua in Status & settings to start watching.')
            return
        now = self.clock()
        try:
            stat = source.stat()
            signature = (str(source.resolve()), stat.st_mtime_ns, stat.st_size)
        except OSError:
            self.emit('Waiting for save', 'The selected addon save is not available. Save in WoW or choose another file.')
            return
        if signature == self.last_success_signature and not force:
            return
        if signature != self.pending_signature:
            self.pending_signature, self.retry_at, self.failures = signature, now + 2, 0
        if not force and now < self.retry_at:
            return
        reading_capture = True
        try:
            raw = roster.read_snapshot(source)
            from local_ai import cached_plan
            local_plan=cached_plan(raw,self.data_dir)
            raw.pop('localAI',None)
            if local_plan:raw['localAI']=local_plan
            row = roster.public_snapshot(raw)
            after = source.stat()
            if (after.st_mtime_ns, after.st_size) != (stat.st_mtime_ns, stat.st_size):
                self.retry_at = now + 2
                return
            with self.lock:
                if self.generation != generation or self.paused or self.stop_event.is_set():
                    return
            self.emit('Syncing', 'Checking GitHub for a newer snapshot.',
                      character=row['character']['name'], captured_at=row['exportedAt'], last_check=utc_now())
            reading_capture = False
            merged, sent = roster.publish(REPOSITORY, 'site/data/characters.json', [row], api=self.api)
            roster.atomic_write(self.data_dir/'roster.json', merged)
            self.last_success_signature = signature
            self.failures = 0
            changes = dict(last_check=utc_now())
            if sent:
                changes['last_publish'] = utc_now()
            self.emit('Published' if sent else 'Up to date',
                      'Snapshot published. GitHub Pages will deploy the update shortly.' if sent else
                      'GitHub already has this snapshot or a newer one. Watching for your next save.', **changes)
        except (ValueError, UnicodeError) as exc:
            self.failures += 1
            self.retry_at = now + min(300, 15 * 2**min(self.failures-1, 5))
            if reading_capture:
                self.emit('Waiting for valid data',
                          'The saved snapshot is incomplete or still being written. In game, run /charout save, then /reload. The last valid website data stays unchanged.')
            else:
                self.emit('Needs attention', 'The public roster returned by GitHub could not be validated. No replacement was uploaded. Retrying automatically.')
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            if self.stop_event.is_set():
                return
            self.failures += 1
            self.retry_at = now + min(300, 15 * 2**min(self.failures-1, 5))
            detail = str(exc) if isinstance(exc, (RuntimeError, roster.GitHubError)) else 'Could not read the save or reach GitHub. Check your connection and local GitHub login.'
            self.emit('Needs attention', detail + ' Retrying automatically.')

    def run(self):
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception:
                # A malformed optional field must not silently end the watcher.
                self.emit('Needs attention', 'The snapshot could not be processed. Choose a fresh addon export or retry after saving in game.')
                self.wake.wait(15)
            self.wake.wait(1)
            self.wake.clear()

    def stop(self):
        self.stop_event.set()
        if hasattr(self.api, 'close'):
            self.api.close()
        self.wake.set()
