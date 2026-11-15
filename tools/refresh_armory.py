"""Refresh public character artwork and item icons for the static armory.

Equipment and progression always remain sourced from Character Ledger. No login,
API credential, or executable page content is used by this optional enrichment.
"""
import argparse
import concurrent.futures
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def image_url(value):
    if not isinstance(value, str):
        return None
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != 'https' or parsed.hostname != 'render.worldofwarcraft.com' or parsed.username or parsed.port:
        return None
    return value if re.search(r'\.(png|jpg|jpeg|webp)$', parsed.path, re.I) else None


def read_url(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'SunderCore/1.0 public character artwork'})
    with urllib.request.urlopen(request, timeout=18) as response:
        raw = response.read(3_000_001)
        if len(raw) > 3_000_000:
            raise ValueError('Response exceeds size limit')
        return raw.decode('utf-8')


def parse_character(page, name, race, character_class):
    match = re.search(r'\bvar\s+characterProfileInitialState\s*=\s*', page)
    if not match:
        raise ValueError('Character data not available')
    data = json.JSONDecoder().raw_decode(page[match.end():])[0]['character']
    expected = (name.casefold(), 'sundercore', 'us', race.casefold(), character_class.casefold())
    actual = tuple(str(v).casefold() for v in (data.get('name'), data.get('surname'), data.get('region'), data.get('race', {}).get('name'), data.get('class', {}).get('name')))
    if actual != expected:
        raise ValueError('Character identity does not match the snapshot')
    media = data.get('media', {})
    # Prefer the original character models used by Forever.
    render = image_url(media.get('main-sd-raw', {}).get('url')) or image_url(media.get('main-raw', {}).get('url'))
    avatar = image_url(media.get('avatar-sd', {}).get('url')) or image_url(media.get('avatar', {}).get('url'))
    if not render:
        raise ValueError('No character render available')
    icons = {}
    equipment = []
    for item in data.get('gear', {}).values():
        item_id = item.get('id')
        if not isinstance(item_id, int) or item_id <= 0:
            continue
        equipment.append(item_id)
        for asset in item.get('media', {}).get('content', {}).get('assets', []):
            icon = image_url(asset.get('value'))
            if asset.get('key') == 'icon' and icon:
                icons[str(item_id)] = {'url': icon, 'source': 'Blizzard'}
    return {
        'render': render, 'avatar': avatar,
        'background': image_url(data.get('render', {}).get('background', {}).get('url')),
        'renderUpdatedAt': data.get('lastUpdatedTimestamp', {}).get('iso8601'),
        'renderEquipment': sorted(equipment),
    }, icons


def character_media(character, previous, checked_at):
    details = character['character']
    slug = urllib.parse.quote(details['name'].lower() + '-sundercore', safe='-')
    url = f'https://worldofwarcraft.blizzard.com/en-us/forever/us/armory/character/{slug}'
    result = {'name': details['name'], 'sourceUrl': url, 'checkedAt': checked_at}
    try:
        media, icons = parse_character(read_url(url), details['name'], details.get('race', ''), details.get('class', ''))
        result.update(media, status='available')
        return character['id'], result, icons
    except (OSError, ValueError, KeyError, TypeError) as error:
        # A temporary upstream failure must not erase an earlier verified render.
        if previous.get('name') == details['name'] and image_url(previous.get('render')):
            result.update({key: previous[key] for key in ('render', 'avatar', 'background', 'renderUpdatedAt', 'renderEquipment') if key in previous})
            result['status'] = 'cached'
        else:
            result['status'] = 'unavailable'
        result['reason'] = 'http-' + str(error.code) if isinstance(error, urllib.error.HTTPError) else 'image-unavailable'
        return character['id'], result, {}


def item_icon(item_id):
    try:
        data = json.loads(read_url(f'https://nether.wowhead.com/forever/tooltip/item/{item_id}'))
        icon = data.get('icon', '')
        if re.fullmatch(r'[a-zA-Z0-9_]+', icon):
            return str(item_id), {'url': f'https://wow.zamimg.com/images/wow/icons/large/{icon.lower()}.jpg', 'source': 'Wowhead'}
    except (OSError, ValueError, TypeError):
        pass
    return str(item_id), None


def refresh(site):
    target = site / 'data' / 'armory.json'
    roster = json.loads((site / 'data' / 'characters.json').read_text(encoding='utf-8'))['characters']
    previous = json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
    checked_at = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    icons = previous.get('icons', {}).copy()
    characters = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(character_media, c, previous.get('characters', {}).get(c['id'], {}), checked_at) for c in roster]
        for future in futures:
            identity, media, found_icons = future.result()
            characters[identity] = media
            icons.update(found_icons)
            print(f"{media['name']}: {media['status']}" + (f" ({media['reason']})" if 'reason' in media else ''))
        ids = {i['itemID'] for c in roster for i in c.get('equipment', []) if isinstance(i.get('itemID'), int) and i['itemID'] > 0}
        missing = sorted(i for i in ids if str(i) not in icons)
        for identity, icon in pool.map(item_icon, missing):
            if icon:
                icons[identity] = icon
    output = {'schemaVersion': 1, 'checkedAt': checked_at, 'characters': characters, 'icons': icons}
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"Armory artwork checked; {len(icons)} item icons available.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, default=ROOT / 'site')
    refresh(parser.parse_args().site)
