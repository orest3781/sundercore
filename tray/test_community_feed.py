import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from email.utils import formatdate
import community_feed as c

NOW=1794962000
CATALOG=json.loads(Path(__file__).with_name('community_catalog.json').read_text(encoding='utf-8'))
URL='https://us.forums.blizzard.com/en/wow/t/cloth-farm/12345'
def rss(title='Gold from linen cloth',body='Compare cloth prices before selling.',when=NOW-100,url=URL):
    return f'<rss><channel><item><title>{title}</title><description>{body}</description><pubDate>{formatdate(when,usegmt=True)}</pubDate><link>{url}</link></item></channel></rss>'.encode()
def search(category=347,when='2026-11-18T00:20:00Z'):
    return json.dumps(dict(topics=[dict(id=12345,title='Gold from cloth',slug='cloth-farm',category_id=category)],
        posts=[dict(topic_id=12345,created_at=when,blurb='Compare linen cloth auction prices.')])).encode()

class CommunityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.addon=self.root/'addon';self.addon.mkdir()
        (self.addon/'CommunityGold.lua').write_text('-- feature')
    def test_feed_only_metadata_and_current_supported_links(self):
        rows=c.parse_feed(rss(body='&lt;b&gt;Gold&lt;/b&gt; |cffff0000 cloth prices'),NOW)
        self.assertEqual(rows[0]['tags'],['cloth']);self.assertNotIn('body',rows[0])
        self.assertEqual(c.parse_feed(rss(when=NOW+1),NOW),[])
        self.assertEqual(c.parse_feed(rss(when=NOW-c.MAX_THREAD_AGE-1),NOW),[])
        self.assertEqual(c.parse_feed(rss(url='https://evil.example/cloth'),NOW),[])
        self.assertEqual(c.parse_feed(rss(title='Blackmaw exploit cloth farm'),NOW),[])
        self.assertTrue(c.parse_feed(rss(title='Gold from cloth and bandages'),NOW),'bandages must not match ban filter')
    def test_search_scope_and_dates(self):
        self.assertEqual(c.parse_search(search(),NOW)[0]['url'],URL)
        self.assertEqual(c.parse_search(search(category=1),NOW),[])
        self.assertEqual(c.parse_search(search(when='2027-01-01T00:00:00Z'),NOW),[])
        with self.assertRaises(ValueError): c.parse_search(b'{}',NOW)
    def test_invalid_xml_size_and_markup(self):
        with self.assertRaises(ValueError): c.parse_feed(b'<!DOCTYPE x><rss/>',NOW)
        with self.assertRaises(ValueError): c.parse_feed(b'X'*(c.MAX_BYTES+1),NOW)
        self.assertEqual(c.clean('<b>test</b> |Hrun:bad|h\n'), 'test Hrun:badh')
        with self.assertRaises(ValueError): c.safe_url('https://user:pass@us.forums.blizzard.com/en/wow/t/a/1')
    def test_data_serialization_cannot_close_string(self):
        value='"; _G.INJECTED=true; --\n雪 |Hbad'
        text=c.lua({'value':value})
        self.assertIn('\\034;',text);self.assertIn('\\010',text);self.assertNotIn('\n',text)
        self.assertNotIn('雪',text)
        with self.assertRaises(ValueError): c.lua(float('nan'))
    def test_source_is_selected_install_only(self):
        source=self.root/'_forever_/WTF/Account/test/SavedVariables/CharacterLedger.lua'
        source.parent.mkdir(parents=True);source.touch()
        addon=self.root/'_forever_/Interface/AddOns/CharacterLedger';addon.mkdir(parents=True)
        (addon/'CharacterLedger.toc').touch();(addon/'CommunityGold.lua').touch()
        self.assertEqual(c.addon_for_source(source),addon)
        self.assertIsNone(c.addon_for_source(self.root/'export.json'))
        self.assertIsNone(c.addon_for_source(str(source).replace('_forever_','_retail_')))
    def test_success_failure_and_review_timestamp(self):
        def fetch(url): return rss() if url==c.FEED_URL else search()
        r=c.refresh(self.addon,self.root,CATALOG,fetch,NOW)
        self.assertTrue(r['success']);self.assertEqual(r['threads'],1)
        body=(self.addon/'CommunityGoldData.lua').read_text()
        self.assertIn(str(CATALOG['reviewedAt']),body)
        def fail(url): raise OSError('offline')
        r=c.refresh(self.addon,self.root,CATALOG,fail,NOW+200)
        self.assertFalse(r['success']);self.assertEqual(r['checkedAt'],NOW);self.assertEqual(r['threads'],1)
        self.assertIn(str(CATALOG['reviewedAt']),(self.addon/'CommunityGoldData.lua').read_text())
    def test_partial_results_remain_honest(self):
        def partial(url):
            if url==c.FEED_URL: return rss()
            raise OSError('unavailable')
        r=c.refresh(self.addon,self.root,CATALOG,partial,NOW)
        self.assertFalse(r['success']);self.assertIn('1/5',r['detail']);self.assertIn('partial',r['detail'])
    def test_source_change_or_pause_during_fetch_keeps_installed_pack(self):
        target=self.addon/'CommunityGoldData.lua';target.write_text('previous')
        c.refresh(self.addon,self.root,CATALOG,lambda url:rss() if url==c.FEED_URL else search(),NOW,lambda:False)
        self.assertEqual(target.read_text(),'previous')
    def test_first_offline_launch_preserves_bundled_pack(self):
        target=self.addon/'CommunityGoldData.lua';target.write_text('previous')
        (self.root/'community-forums.json').write_text('[]')
        def offline(url): raise OSError('offline')
        result=c.refresh(self.addon,self.root,CATALOG,offline,NOW)
        self.assertFalse(result['success']);self.assertEqual(target.read_text(),'previous')
    def test_worker_pause_cadence_and_manual_refresh(self):
        engine=SimpleNamespace(source='source',generation=0,paused=False,stop_event=threading.Event())
        clock=[NOW];messages=[];worker=c.CommunityWorker(engine,self.root,CATALOG,messages.append,clock=lambda:clock[0])
        with patch.object(c,'addon_for_source',return_value=self.addon),patch.object(c,'refresh',return_value=dict(success=True,detail='updated')) as update:
            worker.tick();worker.tick();self.assertEqual(update.call_count,1)
            engine.paused=True;worker.request();worker.tick();self.assertEqual(update.call_count,1)
            engine.paused=False;worker.tick();self.assertEqual(update.call_count,2)
            engine.stop_event.set();worker.request();worker.tick();self.assertEqual(update.call_count,2)

if __name__=='__main__': unittest.main()
