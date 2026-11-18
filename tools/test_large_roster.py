import base64
import unittest
import update_roster as sync
from test_update_roster import snapshot

class LargeRosterTests(unittest.TestCase):
    def test_large_roster_merges_and_preserves_sha(self):
        old=sync.public_snapshot(snapshot(name='Other'))
        existing=sync.merge_roster(None,[old])[0]
        calls=[];sha='a'*40
        def api(endpoint,payload=None):
            calls.append((endpoint,payload))
            if payload is not None:
                self.assertEqual(payload['sha'],sha);return {}
            if '/git/blobs/' in endpoint:
                self.assertTrue(endpoint.endswith(sha))
                return dict(sha=sha,encoding='base64',content=base64.b64encode(sync.encoded(existing).encode()).decode())
            return dict(sha=sha,encoding='none',content='',size=1_300_000)
        merged,sent=sync.publish('test/roster','site/data/characters.json',[sync.public_snapshot(snapshot())],api)
        self.assertTrue(sent);self.assertEqual(len(merged['characters']),2);self.assertEqual(len(calls),3)
    def test_missing_blob_never_turns_into_new_file(self):
        writes=[]
        def api(endpoint,payload=None):
            if payload is not None: writes.append(payload);return {}
            if '/git/blobs/' in endpoint: raise sync.GitHubError('404')
            return dict(sha='a'*40,encoding='none',size=1_300_000)
        with self.assertRaises(ValueError): sync.publish('test/roster','site/data/characters.json',[],api)
        self.assertEqual(writes,[])
    def test_bad_metadata_and_mismatched_blob_fail_closed(self):
        for sha,size in [('../bad',10),('a'*40,sync.MAX_BYTES+1),('a'*40,False)]:
            with self.assertRaises(ValueError):
                sync.publish('test/roster','site/data/characters.json',[],lambda endpoint:dict(sha=sha,size=size,encoding='none'))
        def api(endpoint,payload=None):
            return dict(sha='b'*40 if '/git/blobs/' in endpoint else 'a'*40,size=100,encoding='none')
        with self.assertRaises(ValueError): sync.publish('test/roster','site/data/characters.json',[],api)

if __name__=='__main__':unittest.main()
