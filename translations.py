"""Shared translation catalog for terminal output and the web client."""
import json
from functools import lru_cache
from pathlib import Path

LANGUAGES = ('ru', 'en', 'fr', 'de', 'es')

@lru_cache(maxsize=1)
def catalog():
    return json.loads((Path(__file__).parent / 'static' / 'locales.json').read_text())

def translate(message, language='en'):
    data = catalog()
    return data.get(language, data['en']).get(message, data['en'].get(message, message))
