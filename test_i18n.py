"""Catalog completeness and shared terminal/web translations. No network needed."""
import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path
from translations import translate, LANGUAGES

ROOT = Path(__file__).parent

class TextKeys(HTMLParser):
    def __init__(self):
        super().__init__()
        self.keys = []
    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key.startswith('data-i18n'):
                self.keys.append(value)

class LocalizationTests(unittest.TestCase):
    def test_all_languages_cover_static_and_dynamic_interface(self):
        data = json.loads((ROOT / 'static/locales.json').read_text())
        parser = TextKeys()
        parser.feed((ROOT / 'static/index.html').read_text())
        script = (ROOT / 'static/client.js').read_text()
        keys = parser.keys + re.findall(r"\bt\('([^']+)'\)", script)
        self.assertEqual(set(data), set(LANGUAGES))
        for lang in LANGUAGES:
            self.assertEqual(set(data[lang]), set(data['ru']))
            for key in keys:
                self.assertIn(key, data[lang], (lang, key))
                self.assertTrue(data[lang][key].strip())
            if lang != 'ru':
                for key, value in data[lang].items():
                    self.assertFalse(re.search('[А-Яа-яЁё]', value), (lang, key))
    def test_terminal_translation_and_fallback(self):
        self.assertEqual(translate('Смотреть','en'),'Watch')
        self.assertEqual(translate('Смотреть','fr'),'Regarder')
        self.assertEqual(translate('Смотреть','de'),'Ansehen')
        self.assertEqual(translate('Смотреть','es'),'Ver')
        self.assertEqual(translate('Смотреть','xx'),'Watch')
        self.assertEqual(translate('external diagnostic','fr'),'external diagnostic')

if __name__ == '__main__':
    unittest.main(verbosity=2)
