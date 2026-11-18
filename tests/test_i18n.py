import ast
import copy
import json
import re
import string
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import Handler, Server
from engine import Controller
from i18n import LANGUAGES, Message, catalog, error_message, language_code, localize, message
from test_app import RecordingNetwork, wait_for


class Markup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.keys = set()
        self.ids = []
        self.languages = []
        self.untranslated = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        for key, value in attrs:
            if key.startswith('data-i18n'):
                self.keys.add(value)
        if 'id' in attributes:
            self.ids.append(attributes['id'])
        if 'data-language' in attributes:
            self.languages.append(attributes['data-language'])
        if tag not in {'meta', 'link', 'input', 'br', 'hr'}:
            self.stack.append((tag, attributes))

    def handle_endtag(self, tag):
        while self.stack:
            if self.stack.pop()[0] == tag:
                break

    def handle_data(self, value):
        value = value.strip()
        if not value or not re.search(r'[a-zA-Z\u0400-\u04ff\u4e00-\u9fff]{2}', value):
            return
        if self.stack and self.stack[-1][0] in {'title', 'script', 'style'}:
            return
        if not any('data-i18n' in attrs or 'data-language' in attrs for _, attrs in self.stack):
            self.untranslated.append(value)


class CatalogTests(unittest.TestCase):
    def test_catalog_completeness_and_matching_parameters(self):
        baseline = catalog('en')
        formatter = string.Formatter()
        parameters = lambda text: {field for _, field, _, _ in formatter.parse(text) if field is not None}
        for language in LANGUAGES:
            entries = catalog(language)
            self.assertEqual(set(entries), set(baseline), language)
            for key, value in entries.items():
                self.assertIsInstance(value, str)
                self.assertTrue(value.strip(), (language, key))
                self.assertNotIn('\ufffd', value, (language, key))
                self.assertEqual(parameters(value), parameters(baseline[key]), (language, key))
                self.assertNotRegex(value, r'<(?:script|iframe|img)\b')

    def test_all_source_keys_exist_and_html_is_localized(self):
        keys = set()
        for path in ROOT.glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'message':
                    for arg in node.args[:1]:
                        for literal in ast.walk(arg):
                            if isinstance(literal, ast.Constant) and isinstance(literal.value, str):
                                keys.add(literal.value)
        for path in (ROOT / 'web').glob('*.js'):
            keys.update(re.findall(r"\bt\('([^']+)'", path.read_text(encoding='utf-8')))
        markup = Markup()
        markup.feed((ROOT / 'web/index.html').read_text(encoding='utf-8-sig'))
        keys.update(markup.keys)
        self.assertLessEqual(keys, set(catalog('en')), keys - set(catalog('en')))
        self.assertEqual(markup.untranslated, [])
        self.assertCountEqual(markup.languages, LANGUAGES)
        self.assertEqual(len(markup.ids), len(set(markup.ids)))

    def test_nested_messages_copy_and_user_values(self):
        alias = 'Mi portátil · 我的电脑 · Мой ПК <script>{name}</script>'
        payload = dict(event=message('event_blocked', name=alias), alias=alias,
                       manufacturer='ASUSTek COMPUTER INC.',
                       error=message('err_restore', error=message('err_protected'),
                                     detail=message('err_system', detail='Driver error 5')))
        snapshot = copy.deepcopy(payload)
        for language in LANGUAGES:
            translated = localize(snapshot, language)
            self.assertEqual(translated['alias'], alias)
            self.assertEqual(translated['manufacturer'], payload['manufacturer'])
            self.assertIn(alias, translated['event'])
            self.assertIn(catalog(language)['err_protected'], translated['error'])
            self.assertIn('Driver error 5', translated['error'])
        self.assertIsInstance(snapshot['event'], Message)
        self.assertEqual(payload['event'], snapshot['event'])

    def test_language_normalization_and_errors(self):
        for value, expected in [('pt-BR', 'pt'), ('pt_PT', 'pt'), ('zh-Hans', 'zh'), ('de-DE', 'de'),
                                ('ru', 'ru'), ('../../secret', 'es'), ('xx', 'es')]:
            self.assertEqual(language_code(value), expected)
        localized_error = ValueError(message('err_busy'))
        self.assertEqual(localize(error_message(localized_error), 'fr'), catalog('fr')['err_busy'])
        self.assertIn('5', localize(error_message(OSError('5')), 'zh'))


class LocalizedAPITests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.network = RecordingNetwork()
        self.controller = Controller(self.network, self.directory.name, demo=True)
        wait_for(lambda: self.controller.snapshot()['last_scan'])
        self.server = Server(('127.0.0.1', 0), Handler)
        self.server.token = 'translation-test'
        self.server.controller = self.controller
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.controller.close()
        self.directory.cleanup()

    def request(self, path, language='es', body=None, token='translation-test'):
        request = urllib.request.Request(self.base + path,
                                         data=None if body is None else json.dumps(body).encode(),
                                         headers={'X-Control-Token': token, 'X-Control-Language': language,
                                                  'Content-Type': 'application/json'})
        return self.opener.open(request, timeout=4)

    def test_language_changes_preserve_policy_and_translate_history(self):
        mac = '02:00:00:00:00:14'
        alias = 'Мой телефон 我的手机'
        for action, body in [('rename', dict(mac=mac, name=alias)), ('mode', dict(mode='allowlist')),
                             ('allow', dict(mac=mac, allowed=True))]:
            self.controller.submit(action, body)
            wait_for(lambda: not self.controller.snapshot()['busy'])
        before = self.controller.snapshot()
        affected = self.controller.affected.copy()
        persisted = (Path(self.directory.name) / 'access.json').read_bytes()
        def check(language):
            with self.request('/api/state', language) as response:
                self.assertEqual(response.headers['Content-Language'], language)
                data = json.load(response)
                self.assertEqual(data['language'], language)
                self.assertEqual(data['events'][0]['text'], catalog(language)['event_allowed'].format(mac=mac))
                device = next(d for d in data['devices'] if d['mac'] == mac)
                self.assertEqual(device['alias'], alias)
                self.assertFalse(device['blocked'])
                self.assertEqual(device['manufacturer'], catalog(language)['vendor_private'])
        with ThreadPoolExecutor(max_workers=7) as pool:
            list(pool.map(check, LANGUAGES))
        self.assertEqual(self.controller.affected, affected)
        self.assertEqual(self.controller.snapshot()['policy'], before['policy'])
        self.assertEqual((Path(self.directory.name) / 'access.json').read_bytes(), persisted)

    def test_api_errors_and_catalog_allowlist(self):
        for language in LANGUAGES:
            with self.assertRaises(urllib.error.HTTPError) as rejected:
                self.request('/api/state', language, token='wrong')
            self.assertEqual(rejected.exception.code, 403)
            self.assertEqual(json.load(rejected.exception)['error'], catalog(language)['err_session'])
            with self.assertRaises(urllib.error.HTTPError) as invalid:
                self.request('/api/block', language, body={'mac': 'x', 'blocked': 'yes'})
            self.assertEqual(json.load(invalid.exception)['error'], catalog(language)['err_payload'])
            with self.request(f'/locales/{language}.json') as response:
                self.assertEqual(json.load(response), catalog(language))
        for path in ['/locales/../app.py', '/locales/xx.json', '/locales/en.json/../../datos/session.json']:
            with self.assertRaises(urllib.error.HTTPError) as rejected:
                self.request(path)
            self.assertEqual(rejected.exception.code, 404)
        with self.request('/api/state', 'unsupported') as response:
            self.assertEqual(json.load(response)['language'], 'es')


if __name__ == '__main__':
    unittest.main()
