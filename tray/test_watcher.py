import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import update_roster as roster
from test_update_roster import snapshot
from watcher_core import Watcher, HiddenGitHub


class Remote:
    def __init__(self):
        other=roster.public_snapshot(snapshot(name='OtherCharacter'))
        self.data=roster.merge_roster(None,[other])[0]
        self.calls=0
        self.writes=0
        self.fail=False
        self.corrupt=False

    def __call__(self, endpoint, payload=None):
        self.calls+=1
        if self.fail:
            raise roster.GitHubError('503')
        if payload is None:
            return dict(sha='old',encoding='base64',content=base64.b64encode(
                ('invalid' if self.corrupt else json.dumps(self.data)).encode()).decode())
        self.writes+=1
        self.data=json.loads(base64.b64decode(payload['content']))
        return {}


class WatcherTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.source=self.root/'save.json'
        self.write(snapshot())
        self.events=[]
        self.remote=Remote()
        self.now=0
        self.w=Watcher(self.source,self.root/'cache',self.events.append,self.remote,lambda:self.now)

    def write(self,data): self.source.write_text(json.dumps(data),encoding='utf-8')
    def settle(self):
        self.w.tick();self.now+=3;self.w.tick()

    def test_stable_capture_merges_remote_and_skips_unchanged(self):
        self.w.tick();self.assertEqual(self.remote.calls,0)
        self.now=3;self.w.tick()
        self.assertEqual(self.remote.writes,1)
        self.assertEqual(len(self.remote.data['characters']),2)
        self.assertEqual(self.events[-1]['phase'],'Published')
        self.assertTrue((self.root/'cache'/'roster.json').is_file())
        self.now=40;self.w.tick();self.assertEqual(self.remote.calls,2)
        self.w.sync_now();self.w.tick();self.assertEqual(self.remote.writes,1)
        self.assertEqual(self.events[-1]['phase'],'Up to date')

    def test_pause_resume_and_stop(self):
        self.w.set_paused(True);self.settle();self.assertEqual(self.remote.calls,0)
        self.w.set_paused(False);self.settle();self.assertEqual(self.remote.writes,1)
        self.w.stop();self.w.sync_now();self.w.tick();self.assertEqual(self.remote.calls,2)

    def test_bad_capture_keeps_last_good_and_new_save_resets_backoff(self):
        self.settle()
        before=(self.root/'cache'/'roster.json').read_bytes()
        bad=snapshot(stamp='2026-11-15T12:00:00Z');bad['analysis']['generalBagCapacity']=0
        self.write(bad);self.settle()
        self.assertEqual(self.events[-1]['phase'],'Waiting for valid data')
        self.assertEqual(self.remote.writes,1)
        self.assertEqual((self.root/'cache'/'roster.json').read_bytes(),before)
        self.write(snapshot(stamp='2026-11-15T12:01:00Z'));self.settle()
        self.assertEqual(self.remote.writes,2)

    def test_network_retry_does_not_mark_failed_source_processed(self):
        self.remote.fail=True;self.settle()
        self.assertEqual(self.events[-1]['phase'],'Needs attention')
        calls=self.remote.calls;self.now+=1;self.w.tick();self.assertEqual(self.remote.calls,calls)
        self.remote.fail=False;self.now+=20;self.w.tick()
        self.assertEqual(self.remote.writes,1)

    def test_remote_corruption_is_not_mislabeled_as_game_capture(self):
        self.remote.corrupt=True;self.settle()
        self.assertEqual(self.events[-1]['phase'],'Needs attention')
        self.assertIn('GitHub',self.events[-1]['detail'])
        self.assertEqual(self.remote.writes,0)

    def test_changed_source_while_reading_is_not_uploaded(self):
        original=roster.public_snapshot
        def switch(raw):
            self.w.set_source(self.root/'other.json')
            return original(raw)
        with patch('watcher_core.roster.public_snapshot',side_effect=switch): self.settle()
        self.assertEqual(self.remote.writes,0)

    def test_missing_source_is_actionable_and_no_network(self):
        self.w.source=None;self.w.tick()
        self.assertEqual(self.events[-1]['phase'],'Choose a save')
        self.assertEqual(self.remote.calls,0)

    def test_gh_subprocess_is_hidden_no_shell_and_errors_do_not_echo_secrets(self):
        import subprocess
        proc=unittest.mock.Mock(returncode=1)
        proc.communicate.return_value=('', 'HTTP 401 Authorization: Bearer private-secret')
        client=HiddenGitHub('C:/Program Files/GitHub CLI/gh.exe')
        with patch('watcher_core.subprocess.Popen',return_value=proc) as popen:
            with self.assertRaises(roster.GitHubError) as caught: client('repos/test/name/contents/file')
        self.assertNotIn('private-secret',str(caught.exception))
        self.assertEqual(popen.call_args.kwargs['creationflags'],getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.assertNotIn('shell',popen.call_args.kwargs)
        self.assertEqual(popen.call_args.args[0][0],client.executable)


if __name__=='__main__': unittest.main()
