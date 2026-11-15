import copy
import unittest
from update_roster import normalize_public, project, DAILY


class DailyProjectionTests(unittest.TestCase):
    def test_nested_private_fields_never_publish(self):
        value={'version':1,'day':'2026-11-15','mode':'grind','minutes':45,
               'today':[{'id':'stock:2592','title':'Wool','need':15,'have':2,'playerGUID':'private','localPath':'private'}],
               'projects':[{'recipeID':100,'name':'Bag','remaining':1,'total':2,'completed':1,
                            'materials':[{'id':2592,'need':6,'bag':2,'missing':4,'rawItemString':'private'}]}],
               'sourcePath':'private','settings':{'token':'private'}}
        result=project(value,DAILY)
        self.assertNotIn('private',str(result))
        self.assertEqual(result['projects'][0]['materials'][0]['missing'],4)
        self.assertEqual(result['projects'][0]['completed'],1)

    def test_optional_old_character_roundtrip(self):
        c={'character':{'name':'Example','realm':'Realm','level':1,'xp':0,'xpForNextLevel':10,'moneyCopper':0},'exportedAt':'2026-11-15T00:00:00Z'}
        self.assertNotIn('dailyPlan',normalize_public(c))
        c['dailyPlan']={'version':1,'today':{},'projects':{}}
        result=normalize_public(c)
        self.assertEqual(result['dailyPlan']['today'],[])
        self.assertEqual(result['dailyPlan']['projects'],[])

    def test_bad_quantities_rejected(self):
        for value in (-1,float('nan'),True):
            with self.assertRaises(ValueError):project({'projects':[{'remaining':value}]},DAILY)


if __name__=='__main__':unittest.main()
