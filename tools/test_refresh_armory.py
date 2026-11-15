import json
import unittest
from unittest.mock import patch
import urllib.error

from refresh_armory import parse_character, character_media, image_url, item_icon


class ArmoryMediaTests(unittest.TestCase):
    def fixture(self, **overrides):
        character = dict(name='Scathe', surname='Sundercore', region='us', race={'name': 'Undead'},
                         **{'class': {'name': 'Warlock'}}, media={'main-sd-raw': {'url': 'https://render.worldofwarcraft.com/forever-us/character/6/123-main-sd-raw.png'}},
                         gear={'head': {'id': 123, 'media': {'content': {'assets': [{'key': 'icon', 'value': 'https://render.worldofwarcraft.com/forever-us/icons/56/456.jpg'}]}}}})
        character.update(overrides)
        return '<script>var characterProfileInitialState = ' + json.dumps({'character': character}) + ';window.badCode();</script>'

    def test_reads_json_without_executing_page_content(self):
        media, icons = parse_character(self.fixture(), 'Scathe', 'Undead', 'Warlock')
        self.assertEqual(media['renderEquipment'], [123])
        self.assertIn('123', icons)

    def test_rejects_wrong_character_or_version_identity(self):
        for change in ({'name': 'Someone'}, {'surname': 'Else'}, {'region': 'eu'}, {'race': {'name': 'Tauren'}}, {'class': {'name': 'Mage'}}):
            with self.assertRaises(ValueError):
                parse_character(self.fixture(**change), 'Scathe', 'Undead', 'Warlock')

    def test_rejects_foreign_or_executable_image_urls(self):
        for url in ('javascript:alert(1)', 'https://render.worldofwarcraft.com.evil.test/image.png', 'https://evil.test/image.png', 'https://user@render.worldofwarcraft.com/image.png'):
            self.assertIsNone(image_url(url))

    def test_failure_preserves_previously_verified_image(self):
        character = {'id': 'scathe', 'character': {'name': 'Scathe', 'race': 'Undead', 'class': 'Warlock'}}
        prior = {'name': 'Scathe', 'render': 'https://render.worldofwarcraft.com/image.png', 'renderUpdatedAt': '2026-11-15T13:00:00Z'}
        with patch('refresh_armory.read_url', side_effect=urllib.error.HTTPError('url', 500, 'Error', {}, None)):
            _, result, _ = character_media(character, prior, 'now')
            self.assertEqual(result['status'], 'cached')
            self.assertEqual(result['renderUpdatedAt'], prior['renderUpdatedAt'])
            _, result, _ = character_media(character, {}, 'now')
            self.assertEqual(result['status'], 'unavailable')
            self.assertNotIn('render', result)

    def test_icon_name_is_restricted(self):
        with patch('refresh_armory.read_url', return_value=json.dumps({'icon': '../../bad?data='})):
            self.assertIsNone(item_icon(123)[1])


if __name__ == '__main__':
    unittest.main()
