import copy
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import update_roster as roster
from test_update_roster import snapshot
import local_ai as ai


def sample():
    s=snapshot(stamp=ai.datetime.now(ai.timezone.utc).isoformat())
    s['dailyPlan']={'mode':'gold','today':[dict(id='farm:cloth',title='Gather wool',kind='Farm',status='Travel required',action='Review the camp.',itemID=2592,rank=20)],
        'soon':[dict(id='dungeon',title='Dungeon gear',kind='Gear',action='Find a group.',rank=10)]}
    return s


class LocalAITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.k=ai.Knowledge(self.root)
        self.data={'meta':dict(game='World of Warcraft: Forever',client_build='test',generated_utc='2026-11-18T00:00:00Z'),
            'items':[dict(id=2592,name='Wool Cloth',estimated=0)],'quests':[dict(id=1,name='A quest')],
            'item_sources':[dict(item_id=2592,kind='drop',name='Test mob',zone='Test zone')]}
        self.k.refresh(download=self.data.__getitem__)

    def answer(self,tasks):return dict(recommendations=[dict(taskID=tasks[0]['id'],reasonCode='grinding',evidenceIDs=['item:2592'])])

    def test_no_model_invented_or_prerequisite_actions(self):
        tasks=ai.candidates(sample());evidence=self.k.evidence(sample(),tasks)
        valid=self.answer(tasks);ai.validate_answer(valid,tasks,evidence)
        for task in ('dungeon','invented'):
            bad=copy.deepcopy(valid);bad['recommendations'][0]['taskID']=task
            with self.assertRaises(ValueError):ai.validate_answer(bad,tasks,evidence)
        bad=copy.deepcopy(valid);bad['recommendations'][0]['evidenceIDs']=['fake']
        with self.assertRaises(ValueError):ai.validate_answer(bad,tasks,evidence)
        bad=copy.deepcopy(valid);bad['recommendations']*=2
        with self.assertRaises(ValueError):ai.validate_answer(bad,tasks,evidence)
        bad=copy.deepcopy(valid);bad['recommendations'][0]['reasonCode']='surplus'
        with self.assertRaises(ValueError):ai.validate_answer(bad,tasks,evidence)
        bad=copy.deepcopy(valid);bad['recommendations'][0]['reason']='Guaranteed profit without deposits'
        _,accepted=ai.validate_answer(bad,tasks,evidence)
        self.assertNotIn('Guaranteed',accepted[0]['reason'],'freeform model claims never become UI text')

    def test_failed_refresh_preserves_database(self):
        before=self.k.path.read_bytes();bad=dict(self.data,items=[])
        with self.assertRaises(ValueError):self.k.refresh(download=bad.__getitem__,force=True)
        self.assertEqual(before,self.k.path.read_bytes())
        self.assertEqual(self.k.metadata()['itemCount'],1)

    def test_local_request_schema_unload_and_cache_invalidation(self):
        s=sample();calls=[]
        def request(endpoint,payload):
            calls.append((endpoint,payload));return dict(message=dict(content=json.dumps(self.answer(ai.candidates(s)))))
        plan=ai.analyze(s,self.k,self.root,request=request)
        self.assertEqual(calls[0][0],'/api/chat');self.assertNotIn('cloud',calls[0][1]['model'])
        self.assertEqual(calls[0][1]['keep_alive'],0)
        self.assertEqual(calls[0][1]['format'],ai.SCHEMA)
        ai.install_plan(plan,None,self.root)
        self.assertIsNotNone(ai.cached_plan(s,self.root))
        altered=copy.deepcopy(s);altered['inventory']['bagItemTotals'][0]['count']=99
        self.assertIsNone(ai.cached_plan(altered,self.root))
        altered=copy.deepcopy(s);altered['dailyPlan']['today'][0]['action']='A different cost.'
        self.assertIsNone(ai.cached_plan(altered,self.root))
        s['dailyPlan']['today'][0].update(aiReason='Previous analysis',baseRank=20,rank=10.1)
        self.assertIsNotNone(ai.cached_plan(s,self.root),'AI ranking must not create an analysis feedback loop')
        with patch.object(ai.time,'time',return_value=plan['expiresAt']+1):self.assertIsNone(ai.cached_plan(s,self.root))

    def test_public_privacy_and_same_snapshot_attach(self):
        s=sample();base=roster.public_snapshot(s)
        s['localAI']=dict(schemaVersion=1,generatedAt=100,expiresAt=200,summary='Useful plan',context='private',prompt='private',recommendations=[],evidence=[])
        new=roster.public_snapshot(s);self.assertNotIn('private',json.dumps(new['localAI']))
        new['character']['level']=59
        merged,changed=roster.merge_roster(roster.merge_roster(None,[base])[0],[new])
        self.assertTrue(changed);self.assertEqual(merged['characters'][0]['character']['level'],base['character']['level'])
        self.assertEqual(merged['characters'][0]['localAI']['generatedAt'],100)
        _,changed=roster.merge_roster(merged,[new]);self.assertFalse(changed)

    def test_classic_confidence_and_no_drop_rates(self):
        self.data['items'][0]['estimated']=1;self.data['item_sources'][0]['chance']=99
        self.k.refresh(download=self.data.__getitem__,force=True)
        evidence=self.k.evidence(sample(),ai.candidates(sample()))
        self.assertIn('Classic fallback',evidence[0]['confidence']);self.assertNotIn('chance',evidence[0]['text'])

    def test_unknown_ai_endpoint_rejected_before_network(self):
        with self.assertRaises(ValueError):ai.local_request('https://remote.invalid')

    def test_worker_discards_result_when_source_changes(self):
        from watcher_core import Watcher
        s=sample();source=self.root/'save.json';source.write_text(json.dumps(s))
        engine=Watcher(source,self.root,lambda v:None,api=lambda *a:None)
        worker=ai.AIWorker(engine,self.root,lambda v:None);worker.force=True
        def interrupted(*args):engine.generation+=1;return {}
        with patch.object(ai,'analyze',side_effect=interrupted),patch.object(ai,'install_plan') as install:
            worker.tick();install.assert_not_called()

if __name__=='__main__':unittest.main()
