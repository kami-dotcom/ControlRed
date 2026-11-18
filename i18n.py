"""Shared UTF-8 catalogs and per-response localization; no global session language."""
import functools
import json
from pathlib import Path

LANGUAGES = ('es', 'en', 'de', 'fr', 'zh', 'pt', 'ru')
ROOT = Path(__file__).resolve().parent / 'web' / 'locales'


def language_code(value, default='es'):
    code = str(value or '').replace('_', '-').split(',')[0].split(';')[0].split('-')[0].lower()
    return code if code in LANGUAGES else default


@functools.lru_cache(maxsize=7)
def catalog(language):
    return json.loads((ROOT / (language_code(language) + '.json')).read_text(encoding='utf-8'))


class Message(str):
    """Keep Spanish compatibility in the engine while retaining translation metadata."""
    def __new__(cls, key, params=None):
        params = dict(params or {})
        value = catalog('es')[key].format_map(params)
        result = str.__new__(cls, value)
        result.key = key
        result.params = params
        return result

    def __reduce__(self):
        return Message, (self.key, self.params)


def message(key, **params):
    return Message(key, params)


def error_message(error):
    if len(error.args) == 1 and isinstance(error.args[0], Message):
        return error.args[0]
    # Preserve OS/driver diagnostics verbatim, with a translated explanation.
    return message('err_system', detail=str(error))


def localize(value, language):
    if isinstance(value, Message):
        template = catalog(language).get(value.key, catalog('en')[value.key])
        return template.format_map({key: localize(item, language) for key, item in value.params.items()})
    if isinstance(value, dict):
        return {key: localize(item, language) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [localize(item, language) for item in value]
    return value
