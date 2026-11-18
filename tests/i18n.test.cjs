const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'web/i18n.js'), 'utf8');
const codes = ['es', 'en', 'de', 'fr', 'zh', 'pt', 'ru'];
const catalog = code => JSON.parse(fs.readFileSync(path.join(root, 'web/locales', code + '.json'), 'utf8'));

function setup({saved, browser = ['es'], storageBlocked = false, missing = []} = {}) {
  const storage = new Map(saved ? [['control-language', saved]] : []);
  const requests = [];
  const node = dataset => ({dataset, textContent: '', attrs: {}, selected: false,
    setAttribute(key, value) { this.attrs[key] = value; },
    classList: {toggle() {}}});
  const heading = node({i18n: 'network_devices'});
  const placeholder = node({i18nPlaceholder: 'search_placeholder'});
  const accessible = node({i18nAria: 'language'});
  const buttons = codes.map(code => node({language: code}));
  const document = {documentElement: {}, title: '', querySelectorAll(selector) {
    return ({'[data-i18n]': [heading], '[data-i18n-placeholder]': [placeholder],
      '[data-i18n-aria]': [accessible], '[data-language]': buttons})[selector] || [];
  }};
  const context = vm.createContext({window: {}, document, navigator: {languages: browser},
    localStorage: {
      getItem(key) { if (storageBlocked) throw new Error('Storage unavailable'); return storage.get(key); },
      setItem(key, value) { if (storageBlocked) throw new Error('Storage unavailable'); storage.set(key, value); }
    },
    AbortSignal,
    async fetch(url) {
      requests.push(url);
      const code = url.split('/').pop().replace('.json', '');
      return {ok: !missing.includes(code), json: async () => catalog(code)};
    }});
  vm.runInContext(source, context);
  return {i18n: context.window.ControlI18n, document, heading, placeholder, accessible, buttons, storage, requests};
}

for (const code of codes) {
  test('Switches UI, accessibility and saved preference to ' + code, async () => {
    const ui = setup();
    await ui.i18n.init();
    await ui.i18n.setLanguage(code);
    const expected = catalog(code);
    assert.equal(ui.heading.textContent, expected.network_devices);
    assert.equal(ui.document.title, expected.app_name);
    assert.equal(ui.document.documentElement.lang, code === 'zh' ? 'zh-Hans' : code);
    assert.equal(ui.placeholder.attrs.placeholder, expected.search_placeholder);
    assert.equal(ui.accessible.attrs['aria-label'], expected.language);
    assert.equal(ui.buttons.filter(b => b.attrs['aria-pressed'] === 'true').length, 1);
    assert.equal(ui.buttons.find(b => b.attrs['aria-pressed'] === 'true').dataset.language, code);
    assert.equal(ui.storage.get('control-language'), code);
    const name = '<img src=x onerror=alert(1)> {name} $& 我的电脑';
    assert.equal(ui.i18n.t('event_blocked', {name}), expected.event_blocked.split('{name}').join(name));
    const count = ui.requests.length;
    await ui.i18n.setLanguage(code);
    assert.equal(ui.requests.length, count, 'Loaded catalogs should be reused');
  });
}

test('Restores preference and recognizes regional browser languages', async () => {
  const saved = setup({saved: 'de', browser: ['ru-RU']});
  await saved.i18n.init();
  assert.equal(saved.i18n.language, 'de');
  const automatic = setup({saved: 'unsupported', browser: ['ja', 'pt-BR']});
  await automatic.i18n.init();
  assert.equal(automatic.i18n.language, 'pt');
  assert.equal(automatic.i18n.normalize('zh-Hans-CN'), 'zh');
});

test('Uses English when a preferred language file cannot load', async () => {
  const ui = setup({browser: ['ru-RU'], missing: ['ru']});
  await ui.i18n.init();
  assert.equal(ui.i18n.language, 'en');
  assert.equal(ui.heading.textContent, catalog('en').network_devices);
  await assert.rejects(ui.i18n.setLanguage('ru'));
  assert.equal(ui.i18n.language, 'en');
  assert.equal(await ui.i18n.setLanguage('../data'), false);
});

test('Works with browser storage disabled', async () => {
  const ui = setup({storageBlocked: true, browser: ['fr-FR']});
  await ui.i18n.init();
  assert.equal(ui.i18n.language, 'fr');
  await ui.i18n.setLanguage('zh');
  assert.equal(ui.heading.textContent, catalog('zh').network_devices);
});
