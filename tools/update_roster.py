"""Project Character Ledger snapshots into SunderCore's public roster.

Local-only by default. --publish explicitly writes the public projection to GitHub.
Requires Python 3.10+. No third-party packages; GitHub auth stays inside gh.
"""
from __future__ import annotations
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote
from lua_export import extract

MAX_BYTES = 64 * 1024 * 1024

def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Snapshot exportedAt must be an ISO timestamp')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('Invalid snapshot timestamp') from exc
    if parsed.tzinfo is None:
        raise ValueError('Snapshot timestamp must include a timezone')
    return parsed.astimezone(timezone.utc)

def iso(value):
    return timestamp(value).isoformat(timespec='seconds').replace('+00:00', 'Z')

def integer(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value != int(value) or value < 0:
        raise ValueError('Expected a nonnegative integer')
    return int(value)

def text(value):
    if not isinstance(value, str) or len(value) > 10000:
        raise ValueError('Expected bounded text')
    return value

def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Expected a finite number')
    return value

def boolean(value):
    if not isinstance(value, bool):
        raise ValueError('Expected boolean')
    return value

def project(value, schema):
    """Recursive allowlist. Unknown properties are deliberately never copied."""
    if isinstance(schema, list):
        if value == {}: value = []  # old addon encoders represented empty arrays this way
        if not isinstance(value, list) or len(value) > 20000:
            raise ValueError('Expected bounded array')
        return [project(v, schema[0]) for v in value]
    if isinstance(schema, dict):
        if not isinstance(value, dict): raise ValueError('Expected object')
        return {k: project(value[k], s) for k, s in schema.items() if k in value and value[k] is not None}
    return schema(value)

CHARACTER = {k:text for k in ('name','realm','class','classToken','race','faction','zone','powerType')}
CHARACTER.update({k:integer for k in ('level','xp','xpForNextLevel','restedXP','moneyCopper','maxHealth','maxPower')})
CHARACTER['stats'] = {k:integer for k in ('agility','intellect','spirit','stamina','strength')}
ITEM = dict(itemID=integer,name=text,count=integer,quality=integer,itemLevel=integer,requiredLevel=integer,slot=integer,slotName=text,vendorPriceCopper=integer)
MATERIAL = {k:integer for k in ('id','itemID','bag','bank','missing','need','make','receivedThisOuting','owned','required','count')}
MATERIAL.update({k:text for k in ('name','usesText','action','kind')})
MATERIAL.update({k:boolean for k in ('done','vendor','collect')})
WAYPOINT = dict(mapID=integer,map=integer,x=number,y=number,title=text)
PROJECT = dict(recipeID=integer,name=text,remaining=integer,total=integer,completed=integer,paused=boolean,cancelled=boolean,
    status=text,outputItemID=integer,materials=[MATERIAL])
DAILY_TASK = {k:text for k in ('id','kind','title','status','why','action','source','open')}
DAILY_TASK.update({k:integer for k in ('have','need','itemID','recipeID','questID')})
DAILY_TASK.update({k:boolean for k in ('done','pinned','reviewed','snoozed')})
DAILY = dict(version=integer,day=text,mode=text,minutes=integer,generatedAt=text,
    today=[DAILY_TASK],soon=[DAILY_TASK],someday=[DAILY_TASK],reviewed=[DAILY_TASK],snoozed=[DAILY_TASK],projects=[PROJECT],notices=[text],
    camp=dict(id=text,name=text,zone=text,chosen=boolean))
TARGET = dict(itemID=integer,name=text,requiredLevel=integer,slot=text,source=text,status=text,current=text)
GOAL = {k:text for k in ('id','title','category','status','why','action','actionType','source','button')}
GOAL.update(priority=number,questID=integer,purchaseCost=integer,materials=[MATERIAL],targets=[TARGET],waypoint=WAYPOINT)
SPOT = {k:text for k in ('id','name','zone','note','source','evidence','faction','provider','confidence')}
SPOT.update({k:integer for k in ('low','high','map','npcID','sampleSize','windows','reporters','installs')})
SPOT.update(x=number,y=number,items=[integer],quests=[integer])
FIELD = dict(materials=[MATERIAL],crafts=[dict(recipeID=integer,name=text,remaining=integer)],
    spots=[dict(spot=SPOT,score=number,reasons=[text],evidence=text,comparison=text,travel=text,localZone=boolean,matchCount=integer,
        matchedMaterials=[MATERIAL],history=dict(sessions=integer,seconds=number,xp=integer,kills=integer))],tasks=[text],notices=[text],
    budget={k:integer for k in ('available','rankTotal','reserve','shortfall')},
    dataSource={k:text for k in ('provider','capturedAt','credit','status')})
PROFESSION = dict(name=text,skill=integer,maxSkill=integer,bonusSkill=integer,skillLineID=integer,isPrimary=boolean,recipeScanStatus=text,recipesCapturedAt=text)
QUEST = dict(questID=integer,name=text,level=integer,complete=boolean,failed=boolean,group=boolean,zone=text,
    objectives=[dict(text=text,have=integer,need=integer,finished=boolean)])
SESSION = {k:text for k in ('label','spotID','zone')}
SESSION.update({k:number for k in ('started','ended','seconds','elapsed','segmentAt','pausedAt','lastAt')})
SESSION.update(kills=integer,xp=integer)
def item_counts(value):
    if not isinstance(value, dict): raise ValueError('Expected item count map')
    return {str(k):integer(v) for k,v in value.items() if re.fullmatch(r'[1-9][0-9]*', str(k))}
SESSION.update(receivedLoot=item_counts,loot=item_counts)
PUBLIC = dict(id=text,exportedAt=text,addonVersion=text,character=CHARACTER,
    bags=dict(free=integer,capacity=integer,items=[ITEM]),equipment=[ITEM],professions=[PROFESSION],quests=[QUEST],
    goals=[GOAL],nextSteps=[text],fieldPlan=FIELD,dailyPlan=DAILY,sessions=[SESSION],activeSession=SESSION,
    coverage={k:text for k in ('bags','bank','professions','bankCapturedAt','bankStatus','sessions')})

def identity(character):
    name=text(character.get('name','')).strip();realm=text(character.get('realm','')).strip()
    if not name or not realm: raise ValueError('Character name and realm are required')
    return hashlib.sha256((realm.casefold()+'\0'+name.casefold()).encode('utf-8')).hexdigest()[:24]

def normalize_public(value):
    clean=project(value,PUBLIC)
    clean['id']=identity(clean.get('character',{}))
    clean['exportedAt']=iso(clean.get('exportedAt'))
    c=clean['character']
    for k in ('level','xp','xpForNextLevel','moneyCopper'):
        if k not in c: raise ValueError('Missing character '+k)
    if c['level']<1: raise ValueError('Character level must be positive')
    return clean

def validate_capture(source):
    """Reject logout/teardown captures before they can replace a healthy row.

    An empty inventory still has a real backpack with slots. Zero slots means
    the container APIs were unavailable, not that the character owns no bags.
    XP-to-next-level and money may legitimately be zero and are not sentinels.
    Older exports without raw containers can use positive analysis capacity.
    """
    inventory=source.get('inventory',{});analysis=source.get('analysis',{})
    if not isinstance(inventory,dict) or not isinstance(analysis,dict):
        raise ValueError('Incomplete snapshot: inventory or analysis is unavailable')
    bags=inventory.get('bags',{})
    if not isinstance(bags,dict):raise ValueError('Incomplete snapshot: bag capture is unavailable')
    containers=bags.get('containers',[])
    if containers=={}:containers=[]
    if not isinstance(containers,list):raise ValueError('Incomplete snapshot: invalid bag capture')
    for bag in containers:
        if isinstance(bag,dict) and bag.get('bagID')==0:
            if integer(bag.get('capacity',0))>0:return
            raise ValueError('Incomplete snapshot: backpack reports zero slots, likely logout teardown. Reload while in game to capture fresh data.')
    if integer(analysis.get('generalBagCapacity',0))>0:return
    raise ValueError('Incomplete snapshot: no positive backpack or bag capacity. Reload while in game to capture fresh data.')

def public_snapshot(source):
    if not isinstance(source,dict) or type(source.get('schemaVersion')) is not int or source.get('schemaVersion')!=1: raise ValueError('Unsupported Character Ledger schema')
    validate_capture(source)
    c=project(source.get('character'),CHARACTER)
    inventory=source.get('inventory',{});analysis=source.get('analysis',{})
    result=dict(exportedAt=source.get('exportedAt'),addonVersion=source.get('addonVersion','unknown'),character=c,
        bags=dict(free=analysis.get('generalBagFree'),capacity=analysis.get('generalBagCapacity'),items=inventory.get('bagItemTotals',[])),
        equipment=inventory.get('equipped',[]),professions=source.get('professions',[]),quests=source.get('quests',[]),
        goals=analysis.get('goals',[]),nextSteps=analysis.get('nextSteps',[]),fieldPlan=source.get('fieldPlan',{}),
        sessions=source.get('farmSessions',[]),coverage=project(source.get('coverage',{}),PUBLIC['coverage']))
    bank=inventory.get('bank',{})
    if bank.get('capturedAt'):result['coverage']['bankCapturedAt']=bank['capturedAt']
    if bank.get('status'):result['coverage']['bankStatus']=bank['status']
    result['coverage']['sessions']='Snapshot session summaries' if 'farmSessions' in source else 'Not exported by this addon version'
    if source.get('activeFarmSession'): result['activeSession']=source['activeFarmSession']
    if isinstance(source.get('dailyPlan'),dict): result['dailyPlan']=source['dailyPlan']
    clean=normalize_public(result)
    for m in clean['fieldPlan'].get('materials',[]):
        if not m.get('action'):
            m['action']='Ready' if m.get('done') else 'Collect' if m.get('collect') else 'Withdraw' if m.get('bank',0)>0 else 'Craft' if m.get('make',0)>0 else 'Buy' if m.get('vendor') else 'Farm'
    return clean

def strict_json(value):
    return json.loads(value,parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON value')))

def read_snapshot(path):
    data=path.read_bytes()
    if len(data)>MAX_BYTES: raise ValueError('Snapshot exceeds 64 MiB limit')
    if path.suffix.lower()=='.json' or data.lstrip().startswith(b'{'):
        return strict_json(data.decode('utf-8-sig'))
    return extract(data)

def merge_roster(existing,incoming):
    if existing is None: existing={'schemaVersion':1,'characters':[]}
    if not isinstance(existing,dict) or type(existing.get('schemaVersion')) is not int or existing.get('schemaVersion')!=1 or not isinstance(existing.get('characters'),list):
        raise ValueError('Unsupported public roster schema')
    rows={}
    for raw in existing['characters']:
        row=normalize_public(raw);key=row['id']
        if key not in rows or timestamp(row['exportedAt'])>timestamp(rows[key]['exportedAt']): rows[key]=row
    changed=False
    for raw in incoming:
        row=normalize_public(raw);old=rows.get(row['id'])
        if old is None or timestamp(row['exportedAt'])>timestamp(old['exportedAt']):
            rows[row['id']]=row;changed=True
        # Equal timestamps are deliberately idempotent, even if contents differ.
    ordered=sorted(rows.values(),key=lambda r:(r['character']['realm'].casefold(),r['character']['name'].casefold()))
    result={'schemaVersion':1,'updatedAt':max((r['exportedAt'] for r in ordered),default=None),'characters':ordered}
    return result,changed

def encoded(value): return json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n'

def atomic_write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    raw=encoded(value)
    if path.exists() and path.read_text(encoding='utf-8')==raw:return False
    temp=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,prefix='.roster-',suffix='.tmp',delete=False) as out:
            temp=Path(out.name);out.write(raw);out.flush();os.fsync(out.fileno())
        os.replace(temp,path);return True
    finally:
        if temp and temp.exists():temp.unlink()

class GitHubError(RuntimeError):
    def __init__(self,status):super().__init__('GitHub API request failed'+(' (HTTP '+status+')' if status else '')+'. Check gh authentication and repository access.');self.status=status

def gh_api(endpoint,payload=None):
    command=['gh','api',endpoint,'-H','Accept: application/vnd.github+json']
    if payload is not None:command+=['--method','PUT','--input','-']
    completed=subprocess.run(command,input=encoded(payload) if payload is not None else None,capture_output=True,text=True,encoding='utf-8',timeout=60)
    if completed.returncode:
        match=re.search(r'HTTP\s+(\d{3})',completed.stderr)
        raise GitHubError(match.group(1) if match else None)
    return strict_json(completed.stdout)

def publish(repo,remote_path,incoming,api=gh_api):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):raise ValueError('--repo must be owner/name')
    if remote_path.startswith('/') or any(p in ('','.','..') for p in remote_path.split('/')):raise ValueError('Invalid repository data path')
    endpoint='repos/'+repo+'/contents/'+quote(remote_path,safe='/')
    for attempt in range(3):
        sha=None;existing=None
        try:
            response=api(endpoint)
            if response.get('encoding')!='base64' or not isinstance(response.get('content'),str):raise ValueError('Unexpected GitHub content response')
            existing=strict_json(base64.b64decode(response['content']).decode('utf-8'));sha=response['sha']
        except GitHubError as exc:
            if exc.status!='404':raise
        merged,changed=merge_roster(existing,incoming)
        if existing is not None and not changed:return merged,False
        payload={'message':'Update SunderCore character snapshots','content':base64.b64encode(encoded(merged).encode('utf-8')).decode('ascii')}
        if sha:payload['sha']=sha
        try:api(endpoint,payload);return merged,True
        except GitHubError as exc:
            if exc.status not in ('409','422') or attempt==2:raise
    raise RuntimeError('Concurrent repository changes prevented publication')

def update(args):
    incoming=[public_snapshot(read_snapshot(p)) for p in args.source]
    target=args.site.resolve()/'data'/'characters.json'
    existing=strict_json(target.read_text(encoding='utf-8')) if target.exists() else None
    merged,_=merge_roster(existing,incoming)
    wrote=atomic_write(target,merged)
    sent=False
    if args.publish:
        merged,sent=publish(args.repo,args.remote_path,merged['characters'])
        atomic_write(target,merged)
    print(f'{len(merged["characters"])} characters; local {"updated" if wrote else "unchanged"}; '+('published' if sent else 'remote unchanged' if args.publish else 'local only'))
    return merged

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,action='append',required=True,help='SavedVariables .lua or Character Ledger .json; repeat for more characters')
    parser.add_argument('--site',type=Path,default=Path(__file__).resolve().parents[1]/'site')
    mode=parser.add_mutually_exclusive_group();mode.add_argument('--once',action='store_true',help='Import once (default)');mode.add_argument('--watch',action='store_true',help='Keep watching; stop with Ctrl+C')
    parser.add_argument('--interval',type=float,default=15,help='Watch poll seconds (minimum 2)')
    parser.add_argument('--publish',action='store_true',help='Explicitly publish the public data file to GitHub using gh authentication')
    parser.add_argument('--repo',help='GitHub owner/repository, required for --publish')
    parser.add_argument('--remote-path',default='site/data/characters.json',help='Repository data file path')
    args=parser.parse_args()
    if args.publish and not args.repo:parser.error('--publish requires --repo owner/name')
    if not math.isfinite(args.interval) or args.interval<2:parser.error('--interval must be at least 2 seconds')
    previous=None
    try:
        while True:
            try:
                signatures=[(str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in args.source]
                if signatures!=previous:
                    update(args);previous=signatures
            except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as exc:
                if not args.watch:parser.exit(1,'Update failed: '+str(exc)+'\n')
                print('Update deferred: '+str(exc),file=sys.stderr)
            if not args.watch:break
            time.sleep(args.interval)
    except KeyboardInterrupt:print('Watcher stopped.')

if __name__=='__main__':main()
