import unittest
from update_roster import GEAR, project, normalize_public

class GearProjectionTests(unittest.TestCase):
    def test_signed_stats_and_private_fields(self):
        value={'version':1,'profile':'Affliction','upgrades':[{'itemID':100,'gain':3.9,'currentScore':.9,'candidateScore':4.8,
            'statChanges':[{'stat':'Intellect','before':5,'after':3,'delta':-2,'private':'no'}],
            'waypoint':{'map':1,'x':.5,'y':.25,'private':'no'},'materials':[{'itemID':2592,'count':4,'name':'Wool'}],
            'playerGUID':'private','localPath':'private','rawItemString':'private'}],'account':'private'}
        result=project(value,GEAR)
        self.assertNotIn('private',str(result))
        self.assertEqual(result['upgrades'][0]['statChanges'][0]['delta'],-2)
        self.assertEqual(result['upgrades'][0]['materials'][0]['count'],4)
    def test_unknown_gain_stays_unknown(self):
        result=project({'upgrades':[{'itemID':100,'gain':None,'statChanges':{}}]},GEAR)
        self.assertNotIn('gain',result['upgrades'][0])
        self.assertEqual(result['upgrades'][0]['statChanges'],[])
    def test_nonfinite_score_rejected(self):
        for v in (float('nan'),float('inf'),True):
            with self.assertRaises(ValueError):project({'upgrades':[{'gain':v}]},GEAR)

if __name__=='__main__':unittest.main()
