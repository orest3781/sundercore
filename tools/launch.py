"""Interactive Windows launcher for an explicit SunderCore publication session."""
import argparse
from pathlib import Path
import subprocess
import sys

DEFAULT_GAME = Path('C:/Games/World of Warcraft/_forever_')
REPOSITORY = 'orest3781/sundercore'


def discover(game_root):
    return sorted((p for p in (game_root/'WTF'/'Account').glob('*/SavedVariables/CharacterLedger.lua') if p.is_file()),key=lambda p:str(p).casefold())


def choose_source(candidates,ask=input,say=print):
    if len(candidates)==1:
        say('Found one Character Ledger save.');return candidates[0]
    if not candidates:
        say('No Character Ledger save found in the default Forever installation.')
        entered=ask('Enter the full CharacterLedger.lua or exported JSON path (blank cancels): ').strip().strip('"')
        if not entered:raise ValueError('Cancelled.')
        path=Path(entered).expanduser()
        if not path.is_file():raise ValueError('That snapshot file does not exist.')
        return path
    say('Choose the account folder to read. This folder name stays on this computer:')
    for index,path in enumerate(candidates,1):say(f'  {index}. {path.parent.parent.name}')
    while True:
        value=ask('Account number (blank cancels): ').strip()
        if not value:raise ValueError('Cancelled.')
        if value.isdecimal() and 1<=int(value)<=len(candidates):return candidates[int(value)-1]
        say('Enter one of the listed numbers.')


def command(source,watch=False):
    return [sys.executable,str(Path(__file__).with_name('update_roster.py')),
        '--source',str(source),'--publish','--repo',REPOSITORY,'--watch' if watch else '--once']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group();mode.add_argument('--once',action='store_true');mode.add_argument('--watch',action='store_true')
    parser.add_argument('--source',type=Path,help='Choose an explicit snapshot instead of discovery')
    parser.add_argument('--game-root',type=Path,default=DEFAULT_GAME)
    args=parser.parse_args()
    try:
        source=args.source or choose_source(discover(args.game_root))
        if not source.is_file():raise ValueError('The chosen snapshot file does not exist.')
        print('Publishing public character summaries to '+REPOSITORY+'.')
        print('Use /reload or log out in WoW to save a fresh snapshot.')
        if args.watch:print('Watching until Ctrl+C. No startup task or scheduled task is installed.')
        return subprocess.call(command(source,args.watch))
    except KeyboardInterrupt:
        print('\nStopped.');return 130
    except (OSError,ValueError,EOFError) as exc:
        print('Launch stopped: '+str(exc),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
