"""Public forum metadata -> bounded, escaped addon data; never download Lua code.

Only the selected game install is written. No character/account data is sent to
forums. Reviewed strategy text is bundled locally; fetching a thread does not
renew its review date or turn it into a verified recommendation.
"""
from __future__ import annotations
import html
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

FEED_URL = 'https://us.forums.blizzard.com/en/wow/c/wow-forever/world-of-warcraft-forever-general-discussion/347.rss'
INTERVAL = 6 * 3600  # Starting refresh interval; manual refresh is also available.
MAX_BYTES = 1_500_000
MAX_THREADS = 12
MAX_THREAD_AGE = 14 * 86400
TAGS = {
    'cloth': r'\b(?:cloth|linen|wool|humanoid)\b',
    'bags': r'\b(?:bags?|tailor(?:ing)?)\b',
    'wands': r'\b(?:wands?|enchant(?:ing)?|disenchant(?:ing)?)\b',
    'cooking': r'\b(?:cook(?:ing)?|fish(?:ing)?|meat|eggs?)\b',
}
ECONOMY = re.compile(r'\b(?:gold|silver|money|profit|farm(?:ing)?|auction|sell(?:ing)?|income|vendor(?:ing)?)\b', re.I)
RELEVANT_TITLE = re.compile(r'cloth|linen|wool|tailor|enchant|wand|\bbags?\b|cook|fish|\bmeat\b|gold farm|making gold|gold tips|gold strateg',re.I)
EXCLUDE = re.compile(r'\b(?:exploit\w*|abuse\w*|ban|bans|banned|banning|streamer\w*|bot|bots|botting|dupe\w*|refund|petition)\b|blackmaw', re.I)
SEARCH_TERMS={'cloth':'cloth','bags':'tailoring','wands':'enchanting','cooking':'cooking'}

def search_url(now,tag='cloth'):
    since=datetime.fromtimestamp(now-MAX_THREAD_AGE,timezone.utc).strftime('%Y-%m-%d')
    query='gold '+SEARCH_TERMS[tag]+' category:347 order:latest after:'+since
    return 'https://us.forums.blizzard.com/en/wow/search.json?'+urllib.parse.urlencode({'q':query})


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []
    def handle_data(self, data): self.parts.append(data)


def clean(value, limit=800):
    parser = PlainText(); parser.feed(str(value or ''))
    value = html.unescape(' '.join(parser.parts)).replace('|', '')
    return re.sub(r'\s+', ' ', ''.join(c for c in value if c >= ' ')).strip()[:limit]


def safe_url(value):
    p = urllib.parse.urlsplit(str(value))
    if p.scheme != 'https' or p.port not in (None,443) or p.username or p.password or p.query or p.fragment:
        raise ValueError('Unsupported source URL')
    allowed = (p.hostname == 'us.forums.blizzard.com' and re.fullmatch(r'/en/wow/t/[a-z0-9_-]+/\d+/?',p.path)) or (
        p.hostname == 'www.reddit.com' and re.fullmatch(r'/r/wowforever/comments/[a-z0-9]+/[a-z0-9_]+/?',p.path))
    if not allowed: raise ValueError('Unsupported source URL')
    return p.geturl()


def validate_catalog(value):
    if not isinstance(value,dict) or value.get('schemaVersion') != 1: raise ValueError('Unsupported catalog')
    reviewed = value.get('reviewedAt')
    if type(reviewed) is not int or reviewed <= 0: raise ValueError('Missing review date')
    result = dict(schemaVersion=1,reviewedAt=reviewed,strategies=[],notices=[])
    seen=set()
    for raw in value.get('strategies',[])[:12]:
        sid=raw.get('id')
        if sid not in TAGS or sid in seen: raise ValueError('Unknown or duplicate strategy')
        seen.add(sid)
        row={key:clean(raw.get(key),120 if key=='title' else 800) for key in ('title','summary','steps')}
        if not all(row.values()): raise ValueError('Incomplete strategy')
        row['id']=sid
        for key in ('professions','items'):
            values=raw.get(key,[])
            if not isinstance(values,list) or any(type(n) is not int or not 0<n<10000000 for n in values):
                raise ValueError('Invalid numeric selector')
            row[key]=values[:32]
        row['kinds']=[k for k in raw.get('kinds',[]) if k in ('Farm','Craft','Sell','Disenchant')]
        row['sources']=[dict(title=clean(s.get('title'),120),url=safe_url(s.get('url'))) for s in raw.get('sources',[])[:3]]
        if not row['sources']: raise ValueError('Missing attribution')
        result['strategies'].append(row)
    for row in value.get('notices',[])[:4]:
        result['notices'].append(dict(title=clean(row.get('title'),120),summary=clean(row.get('summary')),url=safe_url(row.get('url'))))
    return result


def parse_feed(data, now):
    if len(data)>MAX_BYTES or b'<!ENTITY' in data.upper() or b'<!DOCTYPE' in data.upper():
        raise ValueError('Unsupported feed')
    root=ET.fromstring(data)
    if root.tag!='rss' or root.find('channel') is None: raise ValueError('Expected RSS')
    rows=[]; seen=set()
    for item in root.findall('./channel/item')[:100]:
        try:
            url=safe_url(item.findtext('link'))
            if not url.startswith('https://us.forums.blizzard.com/'): continue
            posted=int(parsedate_to_datetime(item.findtext('pubDate')).timestamp())
            if not 0<=now-posted<=MAX_THREAD_AGE: continue
            title=clean(item.findtext('title'),150)
            text=clean(item.findtext('description'),12000)
            # Keyword matches identify related discussions only, never profits or rules.
            if EXCLUDE.search(title+' '+text) or not RELEVANT_TITLE.search(title) or not ECONOMY.search(title+' '+text): continue
            tags=[key for key,pattern in TAGS.items() if re.search(pattern,title+' '+text,re.I)]
            if not tags or not title or url in seen: continue
            seen.add(url)
            rows.append(dict(title=' '.join(title.split()[:24]),url=url,postedAt=posted,tags=tags))
        except (ValueError,TypeError,OverflowError,AttributeError): continue
    return sorted(rows,key=lambda r:r['postedAt'],reverse=True)[:MAX_THREADS]


def download(url):
    p=urllib.parse.urlsplit(url)
    if url!=FEED_URL and not (p.scheme=='https' and p.netloc=='us.forums.blizzard.com' and p.path=='/en/wow/search.json'
            and re.fullmatch(r'q=gold\+(?:cloth|tailoring|enchanting|cooking)\+category%3A347\+order%3Alatest\+after%3A\d{4}-\d{2}-\d{2}',p.query)):
        raise ValueError('Unexpected feed endpoint')
    class PublicRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            p=urllib.parse.urlsplit(newurl)
            if p.scheme!='https' or p.hostname!='us.forums.blizzard.com' or not p.path.startswith('/en/wow/c/'):
                raise ValueError('Unexpected feed redirect')
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    req=urllib.request.Request(url,headers={'User-Agent':'SunderCoreCommunity/1.0 (personal journal; public RSS)'})
    with urllib.request.build_opener(PublicRedirect()).open(req,timeout=15) as response:
        data=response.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES: raise ValueError('Feed is too large')
    return data


def parse_search(data,now):
    if len(data)>MAX_BYTES: raise ValueError('Search is too large')
    value=json.loads(data)
    if not isinstance(value,dict) or not isinstance(value.get('posts'),list) or not isinstance(value.get('topics'),list):
        raise ValueError('Expected forum search results')
    topics={t['id']:t for t in value['topics'][:100] if isinstance(t,dict) and type(t.get('id')) is int and t.get('category_id')==347}
    rows={}
    for post in value['posts'][:100]:
        try:
            topic=topics.get(post.get('topic_id'))
            if not topic: continue
            title=clean(topic.get('title'),150);text=clean(post.get('blurb'),12000)
            posted=int(datetime.fromisoformat(post['created_at'].replace('Z','+00:00')).timestamp())
            if not 0<=now-posted<=MAX_THREAD_AGE or EXCLUDE.search(title+' '+text) or not RELEVANT_TITLE.search(title): continue
            tags=[key for key,pattern in TAGS.items() if re.search(pattern,title+' '+text,re.I)]
            if not tags or not ECONOMY.search(title+' '+text): continue
            url=safe_url('https://us.forums.blizzard.com/en/wow/t/'+topic['slug']+'/'+str(topic['id']))
            previous=rows.get(url)
            if previous:
                previous['tags']=sorted(set(previous['tags']+tags));previous['postedAt']=max(previous['postedAt'],posted)
            else: rows[url]=dict(title=' '.join(title.split()[:24]),url=url,postedAt=posted,tags=tags)
        except (ValueError,TypeError,KeyError,AttributeError): continue
    return sorted(rows.values(),key=lambda r:r['postedAt'],reverse=True)[:MAX_THREADS]


def lua(value):
    if value is None: return 'nil'
    if isinstance(value,bool): return 'true' if value else 'false'
    if isinstance(value,(int,float)):
        if not math.isfinite(value): raise ValueError('Invalid number')
        return str(value)
    if isinstance(value,str):
        # Numeric byte escapes avoid Lua/JSON unicode escape incompatibilities.
        return '"'+''.join(chr(b) if 32<=b<127 and b not in (34,92) else '\\%03d'%b for b in value.encode('utf-8'))+'"'
    if isinstance(value,list): return '{'+','.join(lua(v) for v in value)+'}'
    if isinstance(value,dict): return '{'+','.join('['+lua(k)+']='+lua(v) for k,v in sorted(value.items()))+'}'
    raise ValueError('Unsupported data type')


def atomic_text(path,text):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(text,encoding='utf-8');temp.replace(path)


def addon_for_source(source):
    if not source: return None
    source=Path(source).resolve()
    if source.name!='CharacterLedger.lua' or source.parent.name!='SavedVariables': return None
    # .../_forever_/WTF/Account/<account>/SavedVariables/CharacterLedger.lua
    root=source.parents[4]
    if source.parents[2].name!='Account' or source.parents[3].name!='WTF' or root.name!='_forever_': return None
    addon=root/'Interface'/'AddOns'/'CharacterLedger'
    if not (addon/'CharacterLedger.toc').is_file() or not (addon/'CommunityGold.lua').is_file(): return None
    if addon.resolve()!=addon: return None
    return addon


def refresh(addon,data_dir,catalog,fetch=download,now=None,can_install=lambda:True):
    now=int(time.time() if now is None else now)
    pack=validate_catalog(catalog)
    cache=Path(data_dir)/'community-forums.json'
    threads=[];checked=0;status='Feed unavailable; previous successful check retained'
    try:
        old=json.loads(cache.read_text(encoding='utf-8'))
        if not isinstance(old,dict) or not isinstance(old.get('threads'),list): raise ValueError('Invalid cache')
        checked=old.get('checkedAt',0)
        if type(checked) is not int or not 0<checked<=now: checked=0
        for row in old.get('threads',[])[:MAX_THREADS]:
            if not isinstance(row,dict) or not RELEVANT_TITLE.search(str(row.get('title',''))): continue
            if type(row.get('postedAt')) is int and 0<=now-row['postedAt']<=MAX_THREAD_AGE:
                threads.append(dict(title=clean(row.get('title'),150),url=safe_url(row['url']),postedAt=row['postedAt'],tags=[t for t in row.get('tags',[]) if t in TAGS]))
    except (OSError,ValueError,TypeError,KeyError): threads=[];checked=0
    reached=0
    endpoints=[(FEED_URL,parse_feed)]+[(search_url(now,tag),parse_search) for tag in SEARCH_TERMS]
    for url,parser in endpoints:
        try:
            incoming=parser(fetch(url),now);reached+=1
            merged={t['url']:t for t in threads}
            for row in incoming:
                previous=merged.get(row['url'])
                if previous:
                    row['tags']=sorted(set(row['tags']+previous['tags']));row['postedAt']=max(row['postedAt'],previous['postedAt'])
                merged[row['url']]=row
            threads=sorted(merged.values(),key=lambda r:r['postedAt'],reverse=True)[:MAX_THREADS]
        except (OSError,ValueError,ET.ParseError): pass
    success=reached==len(endpoints)
    if reached:
        checked=now;status='Public Forever sources reached: '+str(reached)+'/'+str(len(endpoints))+' (latest feed and profession/material searches)'
        if not success: status+='; partial refresh, previous links retained'
        atomic_text(cache,json.dumps(dict(checkedAt=checked,threads=threads),ensure_ascii=False))
    pack.update(checkedAt=checked,attemptedAt=now,feedStatus=status,threads=threads)
    target=Path(addon)/'CommunityGoldData.lua'
    if not (Path(addon)/'CommunityGold.lua').is_file(): raise ValueError('Install Character Ledger community support first')
    if not can_install(): return dict(success=False,checkedAt=checked,threads=len(threads),detail='Community install paused or source changed. Previous addon data kept.')
    if not reached and not checked and target.is_file():
        return dict(success=False,checkedAt=0,threads=0,detail='Forum sources unavailable. Existing addon pack kept; no successful check was recorded.')
    atomic_text(target,'-- Generated community data. Reload the UI to load changes.\nlocal _,ns=...\nns.CommunityGoldData='+lua(pack)+'\n')
    return dict(success=success,checkedAt=checked,threads=len(threads),detail=status+'. Reload WoW UI to load it.')


class CommunityWorker:
    """Separate from snapshot publishing so forum timeouts cannot delay uploads."""
    def __init__(self,engine,data_dir,catalog,callback,fetch=download,clock=time.time):
        self.engine=engine;self.data_dir=Path(data_dir);self.catalog=catalog;self.callback=callback
        self.fetch=fetch;self.clock=clock;self.next_at=0;self.wake=threading.Event()
    def request(self): self.next_at=0;self.wake.set()
    def tick(self):
        if self.engine.stop_event.is_set() or self.engine.paused or self.clock()<self.next_at: return
        addon=addon_for_source(self.engine.source)
        if addon is None:
            self.next_at=self.clock()+60
            self.callback('Install community support in the selected game addon to enable forum refresh.')
            return
        self.next_at=self.clock()+INTERVAL
        source=self.engine.source;generation=self.engine.generation
        try:
            result=refresh(addon,self.data_dir,self.catalog,self.fetch,self.clock(),
                lambda:not self.engine.paused and not self.engine.stop_event.is_set() and self.engine.source==source and self.engine.generation==generation)
            self.callback(result['detail'])
            if not result['success']: self.next_at=self.clock()+3600
        except (OSError,ValueError):
            self.next_at=self.clock()+3600
            self.callback('Community update could not be installed. Previous addon data is kept; check permissions.')
    def run(self):
        while not self.engine.stop_event.is_set():
            try: self.tick()
            except Exception:
                self.next_at=self.clock()+3600;self.callback('Community refresh failed. Previous addon data is kept; snapshot publishing continues.')
            self.wake.wait(30);self.wake.clear()


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--addon',required=True);p.add_argument('--cache',required=True)
    args=p.parse_args()
    catalog=json.loads(Path(__file__).with_name('community_catalog.json').read_text(encoding='utf-8'))
    print(json.dumps(refresh(Path(args.addon),Path(args.cache),catalog)))
