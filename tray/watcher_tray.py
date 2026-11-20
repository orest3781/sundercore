"""SunderCore Watcher: a windowless Windows tray application."""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import webbrowser

from PIL import Image, ImageDraw
import pystray
from watcher_core import Watcher, WEBSITE, REPOSITORY, discover_sources
from community_feed import CommunityWorker
from local_ai import AIWorker

APP_NAME = 'SunderCore Watcher'
VERSION = '1.4.2'
BG, PANEL, FG, MUTED, ACCENT = '#111611', '#1d251b', '#e7eddf', '#a6b39c', '#d3df9a'


def resource(name):
    return Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / name


def single_instance():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel.CreateMutexW(None, False, 'Local\\SunderCoreWatcher.v1')
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle(handle)
        if '--tray' not in sys.argv:
            ctypes.windll.user32.MessageBoxW(None,
                'SunderCore Watcher is already running.\nLook for the S icon near the Windows clock (it may be under the tray arrow).',
                APP_NAME, 0x40)
        return None
    return handle


def read_config(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


class TrayApp:
    def __init__(self):
        self.data_dir = Path(os.environ['LOCALAPPDATA'])/'SunderCoreWatcher'
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.data_dir/'settings.json'
        self.logger = logging.getLogger('SunderCoreWatcher')
        self.logger.setLevel(logging.INFO)
        handler = RotatingFileHandler(self.data_dir/'watcher.log', maxBytes=256_000, backupCount=2, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
        self.logger.addHandler(handler)
        self.events = queue.Queue()
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(APP_NAME)
        self.root.configure(bg=BG)
        self.root.geometry('690x770')
        self.root.minsize(650, 740)
        self.root.protocol('WM_DELETE_WINDOW', self.hide)
        self.root.report_callback_exception = self.ui_error
        try:
            self.root.iconbitmap(str(resource('SunderCore.ico')))
        except tk.TclError:
            pass
        self.config = read_config(self.config_path)
        source = self.config.get('source')
        if not isinstance(source, str) or not source:
            found = discover_sources()
            source = str(found[0]) if len(found) == 1 else None
            if source:
                self.config['source'] = source
                self.save_config()
        self.engine = Watcher(source, self.data_dir, lambda value: self.events.put(('status', value)))
        catalog=json.loads(resource('community_catalog.json').read_text(encoding='utf-8'))
        self.community=CommunityWorker(self.engine,self.data_dir,catalog,lambda message:self.events.put(('community',message)))
        self.ai=AIWorker(self.engine,self.data_dir,lambda message:self.events.put(('ai',message)),self.config.get('local_ai_enabled',True))
        self.state = dict(self.engine.state)
        self.exiting = False
        self._last_log = None
        self.build_window()
        self.base_icon = Image.open(resource('SunderCore.ico')).convert('RGBA').resize((128,128))
        self.icon = pystray.Icon('SunderCoreWatcher', self.make_icon('#90aa65'), APP_NAME,
            menu=pystray.Menu(
                pystray.MenuItem(lambda item: self.state['phase'], None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem('Status and settings', self.menu_show, default=True),
                pystray.MenuItem('Sync now', self.menu_sync, enabled=lambda item: not self.engine.paused),
                pystray.MenuItem('Refresh community', self.menu_community, enabled=lambda item: not self.engine.paused),
                pystray.MenuItem('Analyze now with local AI', self.menu_ai, enabled=lambda item: self.ai.enabled and not self.engine.paused),
                pystray.MenuItem(lambda item: 'Resume watching' if self.engine.paused else 'Pause watching', self.menu_pause),
                pystray.MenuItem('Open SunderCore website', self.menu_website),
                pystray.MenuItem('Open log', self.menu_log),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem('Exit', self.menu_exit)))
        self.icon_thread = threading.Thread(target=self.icon.run, kwargs={'setup':self.tray_ready}, daemon=True, name='TrayIcon')
        self.icon_thread.start()
        self.worker = threading.Thread(target=self.engine.run, daemon=True, name='SnapshotWatcher')
        self.worker.start()
        self.community_thread=threading.Thread(target=self.community.run,daemon=True,name='CommunityForums')
        self.community_thread.start()
        self.ai_thread=threading.Thread(target=self.ai.run,daemon=True,name='LocalAdvisor')
        self.ai_thread.start()
        self.root.after(150, self.process_events)
        self.root.after(400, self.initial_display)

    def make_icon(self, color):
        result = self.base_icon.copy()
        draw = ImageDraw.Draw(result)
        draw.ellipse((91,91,126,126), fill=color, outline='#111611', width=5)
        return result

    def save_config(self):
        temp = self.config_path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.config, indent=2)+'\n', encoding='utf-8')
        temp.replace(self.config_path)

    def label(self, parent, text='', color=FG, size=10, **kwargs):
        return tk.Label(parent, text=text, bg=parent.cget('bg'), fg=color, font=('Segoe UI', size), **kwargs)

    def button(self, parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command, bg=ACCENT if primary else '#2c3927',
                         fg=BG if primary else FG, activebackground='#aaba7d', activeforeground=BG,
                         relief='flat', padx=15, pady=9, font=('Segoe UI',10), cursor='hand2')

    def build_window(self):
        wrap = tk.Frame(self.root, bg=BG, padx=28, pady=22)
        wrap.pack(fill='both', expand=True)
        self.label(wrap, 'SUNDERCORE  /  WATCHER', ACCENT, 10, anchor='w').pack(fill='x')
        self.label(wrap, 'Your character journal, kept current.', FG, 20, anchor='w').pack(fill='x', pady=(8,18))
        status_box = tk.Frame(wrap, bg=PANEL, padx=18, pady=14)
        status_box.pack(fill='x')
        self.phase_label = self.label(status_box, 'Starting', ACCENT, 15, anchor='w')
        self.phase_label.pack(fill='x')
        self.detail_label = self.label(status_box, 'Looking for the addon save…', MUTED, 10, wraplength=530, justify='left', anchor='w')
        self.detail_label.pack(fill='x', pady=(8,10))
        self.last_label = self.label(status_box, 'No snapshots checked yet.', MUTED, 9, justify='left', anchor='w')
        self.last_label.pack(fill='x')
        self.label(wrap, 'ADDON SAVE', MUTED, 9, anchor='w').pack(fill='x', pady=(19,7))
        row = tk.Frame(wrap, bg=BG)
        row.pack(fill='x')
        self.source_var = tk.StringVar(value=str(self.engine.source or 'No file selected'))
        entry = tk.Entry(row, textvariable=self.source_var, state='readonly', readonlybackground=PANEL,
                         fg=FG, relief='flat', font=('Segoe UI',9))
        entry.pack(side='left', fill='x', expand=True, ipady=9, padx=(0,8))
        self.button(row, 'Choose file', self.choose_source).pack(side='right')
        self.label(wrap, 'Publishes to '+REPOSITORY+' using your GitHub CLI login.', MUTED, 9, anchor='w').pack(fill='x', pady=(9,0))
        self.label(wrap, 'IN GAME', ACCENT, 9, anchor='w').pack(fill='x', pady=(20,6))
        self.label(wrap, 'Run /charout save, then /reload or log out.\nValid saves publish automatically; GitHub Pages then deploys them.', FG,10,
                   anchor='w', justify='left').pack(fill='x')
        self.community_label=self.label(wrap,'Community: checking the public Forever forum feed…',MUTED,9,wraplength=580,justify='left',anchor='w')
        self.community_label.pack(fill='x',pady=(12,0))
        self.ai_label=self.label(wrap,'Local AI: '+('waiting for a settled snapshot' if self.ai.enabled else 'paused'),MUTED,10,wraplength=600,justify='left',anchor='w')
        self.ai_label.pack(fill='x',pady=(12,0))
        ai_actions=tk.Frame(wrap,bg=BG);ai_actions.pack(fill='x',pady=(8,0))
        self.button(ai_actions,'Analyze now',self.ai.request).pack(side='left',padx=(0,8))
        self.ai_toggle=self.button(ai_actions,'Pause local AI' if self.ai.enabled else 'Enable local AI',self.toggle_ai)
        self.ai_toggle.pack(side='left')
        actions = tk.Frame(wrap, bg=BG)
        actions.pack(fill='x', pady=(22,12))
        self.sync_button = self.button(actions, 'Sync now', self.engine.sync_now, True)
        self.sync_button.pack(side='left', padx=(0,8))
        self.pause_button = self.button(actions, 'Pause', self.toggle_pause)
        self.pause_button.pack(side='left', padx=(0,8))
        self.button(actions, 'Open website', lambda: webbrowser.open(WEBSITE)).pack(side='left')
        bottom = tk.Frame(wrap, bg=BG)
        bottom.pack(fill='x', side='bottom')
        self.label(bottom, 'Close this window to keep watching in the tray.\nManage automatic startup in Windows Startup apps.', MUTED,9, justify='left').pack(side='left')
        self.button(bottom, 'Hide to tray', self.hide).pack(side='right')

    def initial_display(self):
        start_hidden = '--tray' in sys.argv or self.config.get('start_minimized', False)
        if '--show' in sys.argv or (not start_hidden and (not self.config.get('welcomed') or not self.engine.source)):
            self.show()
            self.config['welcomed'] = True
            self.save_config()
        self.logger.info('Started %s; status window is %s.',
                         'in tray' if self.root.state()=='withdrawn' else 'with status window', self.root.state())

    def tray_ready(self, icon):
        icon.visible = True
        self.logger.info('Tray icon ready.')

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide(self):
        self.root.withdraw()

    def choose_source(self):
        selected = filedialog.askopenfilename(parent=self.root, title='Choose your Character Ledger save',
            initialdir=str(self.engine.source.parent) if self.engine.source else 'C:/Games/World of Warcraft/_forever_/WTF/Account',
            filetypes=[('Character Ledger save', '*.lua *.json'), ('All files','*.*')])
        if selected:
            self.config['source'] = selected
            self.save_config()
            self.source_var.set(selected)
            self.engine.set_source(selected)
            self.community.request()
            self.ai.request()

    def toggle_ai(self):
        self.ai.set_enabled(not self.ai.enabled)
        self.config['local_ai_enabled']=self.ai.enabled;self.save_config()
        self.ai_toggle.config(text='Pause local AI' if self.ai.enabled else 'Enable local AI')
        self.ai_label.config(text='Local AI: '+('enabled; waiting for a settled snapshot' if self.ai.enabled else 'paused; an active request may finish but will be discarded'))
        self.icon.update_menu()

    def toggle_pause(self):
        self.engine.set_paused(not self.engine.paused)

    def process_events(self):
        if self.exiting:
            return
        try:
            while True:
                action, value = self.events.get_nowait()
                if action == 'status':
                    self.apply_status(value)
                elif action == 'show': self.show()
                elif action == 'sync': self.engine.sync_now()
                elif action == 'community': self.community_label.config(text='Community: '+value);self.logger.info('Community: %s',value)
                elif action == 'refresh_community': self.community.request()
                elif action == 'ai': self.ai_label.config(text='Local AI: '+value);self.logger.info('Local AI: %s',value)
                elif action == 'analyze': self.ai.request()
                elif action == 'pause': self.toggle_pause()
                elif action == 'website': webbrowser.open(WEBSITE)
                elif action == 'log': os.startfile(self.data_dir/'watcher.log')
                elif action == 'exit': self.quit(); return
        except queue.Empty:
            pass
        self.root.after(150, self.process_events)

    def apply_status(self, value):
        self.state = value
        phase = value['phase']
        color = '#8a9185' if phase=='Paused' else '#d7b56c' if phase in ('Waiting for valid data','Needs attention','Choose a save','Waiting for save') else ACCENT
        self.phase_label.config(text=phase, fg=color)
        self.detail_label.config(text=value['detail'])
        lines=[]
        if value['character']: lines.append('Character: '+value['character']+'  •  Captured '+self.local_time(value['captured_at']))
        if value['last_check']: lines.append('Last check: '+self.local_time(value['last_check']))
        if value['last_publish']: lines.append('Last published: '+self.local_time(value['last_publish']))
        self.last_label.config(text='\n'.join(lines) or 'Waiting for the first valid saved snapshot.')
        self.pause_button.config(text='Resume' if value['paused'] else 'Pause')
        self.sync_button.config(state='disabled' if value['paused'] or phase=='Syncing' else 'normal')
        self.icon.title = (APP_NAME+' — '+phase)[:127]
        self.icon.icon = self.make_icon(color)
        self.icon.update_menu()
        marker = (phase, value['detail'], value['captured_at'])
        if marker != self._last_log:
            self.logger.info('%s: %s', phase, value['detail'])
            self._last_log = marker

    @staticmethod
    def local_time(value):
        from datetime import datetime
        try: return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone().strftime('%b %d, %I:%M:%S %p')
        except (ValueError,AttributeError): return value or '—'

    def menu_show(self, icon, item): self.events.put(('show',None))
    def menu_sync(self, icon, item): self.events.put(('sync',None))
    def menu_community(self, icon, item): self.events.put(('refresh_community',None))
    def menu_ai(self, icon, item): self.events.put(('analyze',None))
    def menu_pause(self, icon, item): self.events.put(('pause',None))
    def menu_website(self, icon, item): self.events.put(('website',None))
    def menu_log(self, icon, item): self.events.put(('log',None))
    def menu_exit(self, icon, item): self.events.put(('exit',None))

    def ui_error(self, typ, value, tb):
        self.logger.exception('Window error', exc_info=(typ,value,tb))
        messagebox.showerror(APP_NAME, 'An interface error occurred. See Open log in the tray menu.', parent=self.root)

    def quit(self):
        self.exiting = True
        self.engine.stop()
        self.community.wake.set()
        self.ai.wake.set()
        self.icon.visible = False
        self.icon.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    if os.name != 'nt':
        raise RuntimeError('SunderCore Watcher is a Windows application.')
    handle = single_instance()
    if handle is None:
        return
    try:
        try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (OSError,AttributeError): pass
        TrayApp().run()
    except Exception as exc:
        ctypes.windll.user32.MessageBoxW(None, 'SunderCore Watcher could not start.\n'+str(exc), APP_NAME, 0x10)
        raise
    finally:
        kernel=ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        kernel.CloseHandle(handle)


if __name__=='__main__':
    main()
