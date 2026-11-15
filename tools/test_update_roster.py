"""Run: python -m unittest discover -s tools -p 'test_*.py' (from SunderCore)."""
import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest
import update_roster as sync
from lua_export import extract, read_lua_string
import launch

def snapshot(name='Scathe', stamp='2026-11-15T10:00:00Z', realm='Forever Test'):
    return {'schemaVersion':1,'addonVersion':'1.3.0','exportedAt':stamp,
        'character':{'name':name,'realm':realm,'class':'Warlock','classToken':'WARLOCK','level':22,'xp':24638,'xpForNextLevel':27300,'moneyCopper':3247,'guid':'Player-private'},
        'analysis':{'generalBagFree':9,'generalBagCapacity':54,'goals':[],'nextSteps':[]},
        'inventory':{'bagItemTotals':[{'itemID':2592,'name':'Wool Cloth','count':1}],
            'equipped':[{'itemID':123,'name':'Safe armor','slot':5,'itemString':'item:123:Player-private','secret':'no'}]},
        'fieldPlan':{'materials':[{'id':2592,'name':'Wool Cloth','bag':1,'need':15,'missing':14}],
            'budget':{'available':3247,'reserve':0}},
        'professions':[{'name':'Tailoring','skill':94,'maxSkill':150,'account':'private'}],
        'account':'private','path':'C:/Users/private','raw':{'token':'private'},'quests':[]}

def lua(value):
    # Lua quoted literals use the same double quote/backslash escaping for this fixture.
    return ('CharacterLedgerJSON = '+json.dumps(json.dumps(value,ensure_ascii=False),ensure_ascii=False)+'\n').encode()

class ProjectionTests(unittest.TestCase):
    def test_public_allowlist_and_exact_stats(self):
        p=sync.public_snapshot(snapshot());raw=sync.encoded(p)
        self.assertNotIn('private',raw);self.assertNotIn('itemString',raw)
        self.assertEqual((p['character']['xp'],p['character']['xpForNextLevel'],p['character']['moneyCopper']),(24638,27300,3247))
        self.assertEqual(p['bags']['free'],9);self.assertEqual(p['bags']['capacity'],54)
        self.assertEqual(p['professions'][0]['skill'],94)
        self.assertEqual(p['fieldPlan']['materials'][0]['action'],'Farm')
    def test_missing_bag_data_is_unknown_not_zero(self):
        s=snapshot();del s['analysis']['generalBagFree'];del s['analysis']['generalBagCapacity']
        s['inventory']['bags']={'containers':[{'bagID':0,'capacity':20,'items':[]}]}
        p=sync.public_snapshot(s);self.assertNotIn('free',p['bags']);self.assertNotIn('capacity',p['bags'])
        s['analysis'].update(generalBagFree=0,generalBagCapacity=0)
        p=sync.public_snapshot(s);self.assertEqual(p['bags']['free'],0);self.assertEqual(p['bags']['capacity'],0)
    def test_teardown_does_not_replace_valid_character(self):
        good=sync.public_snapshot(snapshot());roster,_=sync.merge_roster(None,[good])
        bad=snapshot(stamp='2026-11-15T11:00:00Z')
        bad['character'].update(xpForNextLevel=0,moneyCopper=0)
        bad['analysis'].update(generalBagFree=0,generalBagCapacity=0)
        bad['inventory'].update(bagItemTotals=[],bags={'containers':[{'bagID':0,'capacity':0,'freeSlots':0,'items':[]}]})
        with self.assertRaisesRegex(ValueError,'Incomplete snapshot'):sync.public_snapshot(bad)
        self.assertEqual(roster['characters'][0]['character']['moneyCopper'],3247)
        self.assertEqual(roster['characters'][0]['exportedAt'],'2026-11-15T10:00:00Z')
        bad['analysis']['generalBagCapacity']=54
        with self.assertRaisesRegex(ValueError,'Incomplete snapshot'):sync.public_snapshot(bad)
    def test_empty_inventory_zero_money_max_level_xp_are_valid(self):
        s=snapshot();s['character'].update(level=60,xp=0,xpForNextLevel=0,moneyCopper=0)
        s['inventory'].update(bagItemTotals=[],bags={'containers':[{'bagID':0,'capacity':20,'freeSlots':20,'items':[]}]})
        s['analysis'].update(generalBagFree=20,generalBagCapacity=20)
        p=sync.public_snapshot(s);self.assertEqual(p['character']['xpForNextLevel'],0);self.assertEqual(p['character']['moneyCopper'],0);self.assertEqual(p['bags']['items'],[])
    def test_safe_escaping_and_comments(self):
        s=snapshot('Séan "quoted" \\ name');data=b'-- CharacterLedgerJSON = "bad"\n--[[\nCharacterLedgerJSON = "bad"\n]]\n'+lua(s)
        self.assertEqual(extract(data),s)
        self.assertEqual(read_lua_string(b'"A\\065\\x42\\z  C"',0),'AABC')
        self.assertEqual(extract(('CharacterLedgerJSON = [=[\n'+json.dumps(s)+']=]\n').encode()),s)
    def test_never_executes_lua_expressions(self):
        for data in (b'CharacterLedgerJSON=os.execute("bad")',lua(snapshot()).rstrip()+b' .. os.execute("bad")',b'CharacterLedgerJSON="unterminated'):
            with self.assertRaises(ValueError):extract(data)
    def test_bad_schema_numeric_timestamp(self):
        for key,value in [('schemaVersion',99),('exportedAt','yesterday')]:
            s=snapshot();s[key]=value
            with self.assertRaises(ValueError):sync.public_snapshot(s)
        for value in (-1,float('nan'),True,'3247'):
            s=snapshot();s['character']['moneyCopper']=value
            with self.assertRaises(ValueError):sync.public_snapshot(s)
        with self.assertRaises(ValueError):sync.strict_json('{"x":NaN}')
    def test_merge_new_stale_equal_and_realm_separation(self):
        first=sync.public_snapshot(snapshot());roster,changed=sync.merge_roster(None,[first]);self.assertTrue(changed)
        stale=sync.public_snapshot(snapshot(stamp='2026-11-14T10:00:00Z'));stale['character']['xp']=999
        merged,changed=sync.merge_roster(roster,[stale,first]);self.assertFalse(changed);self.assertEqual(merged['characters'][0]['character']['xp'],24638)
        new=sync.public_snapshot(snapshot(name='SCATHE',stamp='2026-11-15T10:01:00Z'));new['character']['xp']=25000
        other=sync.public_snapshot(snapshot(realm='Other realm'));merged,changed=sync.merge_roster(merged,[new,other])
        self.assertEqual(len(merged['characters']),2);self.assertTrue(changed)
        self.assertEqual({c['character']['xp'] for c in merged['characters']},{24638,25000})
    def test_timezone_order(self):
        first=sync.public_snapshot(snapshot(stamp='2026-11-15T06:00:00-05:00'))
        self.assertEqual(first['exportedAt'],'2026-11-15T11:00:00Z')
        merged,_=sync.merge_roster(None,[first]);merged,changed=sync.merge_roster(merged,[sync.public_snapshot(snapshot())]);self.assertFalse(changed)
    def test_atomic_write_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'data/characters.json';value={'schemaVersion':1,'characters':[]}
            self.assertTrue(sync.atomic_write(p,value));self.assertFalse(sync.atomic_write(p,value));self.assertEqual(json.loads(p.read_text()),value)

class PublishTests(unittest.TestCase):
    def test_remote_merge_and_conflict_retry(self):
        remote,_=sync.merge_roster(None,[sync.public_snapshot(snapshot(name='Remote'))]);state={'roster':remote,'sha':'one','puts':0}
        def api(endpoint,payload=None):
            self.assertEqual(endpoint,'repos/test/roster/contents/site/data/characters.json')
            if payload is None:return {'sha':state['sha'],'encoding':'base64','content':base64.b64encode(sync.encoded(state['roster']).encode()).decode()}
            state['puts']+=1
            if state['puts']==1:
                state['roster'],_=sync.merge_roster(state['roster'],[sync.public_snapshot(snapshot(name='Concurrent'))]);state['sha']='two';raise sync.GitHubError('409')
            self.assertEqual(payload['sha'],'two');state['roster']=json.loads(base64.b64decode(payload['content']));return {}
        merged,sent=sync.publish('test/roster','site/data/characters.json',[sync.public_snapshot(snapshot())],api)
        self.assertTrue(sent);self.assertEqual(state['puts'],2);self.assertEqual({r['character']['name'] for r in merged['characters']},{'Scathe','Remote','Concurrent'})
        _,sent=sync.publish('test/roster','site/data/characters.json',[sync.public_snapshot(snapshot())],api)
        self.assertFalse(sent);self.assertEqual(state['puts'],2)
    def test_malformed_remote_not_overwritten(self):
        def api(endpoint,payload=None):
            self.assertIsNone(payload)
            return {'encoding':'base64','sha':'one','content':base64.b64encode(b'{bad json').decode()}
        with self.assertRaises(ValueError):sync.publish('test/roster','site/data/characters.json',[sync.public_snapshot(snapshot())],api)
    def test_failure_message_never_echoes_secret(self):
        self.assertNotIn('token',str(sync.GitHubError('401')))

class LauncherTests(unittest.TestCase):
    def test_discovery_and_multiple_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for account in ('ALPHA','BETA'):
                p=root/'WTF'/'Account'/account/'SavedVariables'/'CharacterLedger.lua';p.parent.mkdir(parents=True);p.write_text('')
            choices=launch.discover(root);self.assertEqual(len(choices),2)
            selected=launch.choose_source(choices,ask=lambda _: '2',say=lambda _:None)
            self.assertEqual(selected.parent.parent.name,'BETA')
            self.assertEqual(launch.choose_source(choices[:1],ask=lambda _:self.fail('Unexpected prompt'),say=lambda _:None),choices[0])
    def test_explicit_launch_has_no_shell_or_credentials(self):
        p=Path('C:/Game with spaces/SavedVariables/CharacterLedger.lua')
        cmd=launch.command(p,True)
        self.assertIn(str(p),cmd);self.assertIn('--watch',cmd);self.assertIn('--publish',cmd)
        self.assertEqual(cmd[cmd.index('--repo')+1],'orest3781/sundercore')

if __name__=='__main__':unittest.main()
