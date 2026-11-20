import copy
import unittest
import update_roster as sync
from test_update_roster import snapshot

class JournalProjectionTests(unittest.TestCase):
    def sample(self):
        raw=snapshot()
        raw['dailyPlan']={'version':3,'listSize':3,'personal':[{'id':1,'text':'Repair before grinding','done':False,'path':'PRIVATE'}],
            'focus':{'id':'outing:camp','title':'Chosen camp','kind':'Farm','open':'Outing','guid':'PRIVATE',
                'spot':{'id':'camp','name':'Chosen camp','zone':'Hillsbrad','x':.5,'y':.6,'account':'PRIVATE'}}}
        raw['fieldPlan']['materials'][0].update(owned=12,bankSeen=4,bankAt='2026-11-15T09:00:00Z',
            allocations=[{'owner':'Saved project','need':15,'bag':1,'bank':4,'make':0,'missing':10,'path':'PRIVATE'}])
        return raw
    def test_bounded_public_journal_and_nested_privacy(self):
        clean=sync.public_snapshot(self.sample())
        self.assertEqual(clean['dailyPlan']['focus']['spot']['x'],.5)
        self.assertEqual(clean['dailyPlan']['personal'][0]['done'],False)
        self.assertEqual(clean['fieldPlan']['materials'][0]['owned'],12)
        self.assertNotIn('PRIVATE',sync.encoded(clean))
        self.assertEqual(clean['projectionVersion'],2)
    def test_equal_capture_enriches_only_new_fields(self):
        new=sync.public_snapshot(self.sample());old=copy.deepcopy(new)
        old.pop('projectionVersion');old['dailyPlan'].pop('focus');old['dailyPlan'].pop('personal');old['dailyPlan'].pop('listSize')
        for key in ('allocations','bankSeen','bankAt'):old['fieldPlan']['materials'][0].pop(key)
        new['character']['moneyCopper']=999999;new['fieldPlan']['materials'][0]['bag']=999
        merged,changed=sync.merge_roster({'schemaVersion':1,'characters':[old]},[new]);result=merged['characters'][0]
        self.assertTrue(changed);self.assertEqual(result['character']['moneyCopper'],old['character']['moneyCopper'])
        self.assertEqual(result['fieldPlan']['materials'][0]['bag'],1)
        self.assertEqual(result['dailyPlan']['focus']['title'],'Chosen camp')
        self.assertEqual(result['fieldPlan']['materials'][0]['allocations'][0]['bank'],4)
        self.assertFalse(sync.merge_roster(merged,[new])[1])
    def test_newer_capture_can_clear_focus_and_personal_tasks(self):
        old=sync.public_snapshot(self.sample());new=sync.public_snapshot(snapshot(stamp='2026-11-16T10:00:00Z'))
        new['dailyPlan']={'version':3,'listSize':3,'personal':[]}
        merged,_=sync.merge_roster({'schemaVersion':1,'characters':[old]},[new])
        self.assertNotIn('focus',merged['characters'][0]['dailyPlan']);self.assertEqual(merged['characters'][0]['dailyPlan']['personal'],[])
