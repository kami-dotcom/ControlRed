'use strict';
window.ControlI18n = (() => {
  const languages = ['es', 'en', 'de', 'fr', 'zh', 'pt', 'ru'];
  const locales = {es: 'es', en: 'en', de: 'de', fr: 'fr', zh: 'zh-Hans', pt: 'pt', ru: 'ru'};
  const catalogs = new Map();
  let language = 'es';
  function normalize(value) {
    const code = String(value || '').toLowerCase().replaceAll('_', '-').split('-')[0];
    return languages.includes(code) ? code : null;
  }
  function preferred() {
    try {
      const saved = normalize(localStorage.getItem('control-language'));
      if (saved) return saved;
    } catch {}
    return (navigator.languages || [navigator.language]).map(normalize).find(Boolean) || 'en';
  }
  async function load(code) {
    if (!catalogs.has(code)) {
      const response = await fetch('/locales/' + code + '.json', {signal: AbortSignal.timeout(8000)});
      if (!response.ok) throw new Error('Translation file unavailable: ' + code);
      const entries = await response.json();
      catalogs.set(code, entries);
    }
    return catalogs.get(code);
  }
  function t(key, params = {}) {
    const template = catalogs.get(language)?.[key] ?? catalogs.get('en')?.[key] ?? key;
    return template.replace(/\{(\w+)\}/g, (match, name) => Object.hasOwn(params, name) ? String(params[name]) : match);
  }
  function apply() {
    document.documentElement.lang = locales[language];
    document.title = t('app_name');
    document.querySelectorAll('[data-i18n]').forEach(node => { node.textContent = t(node.dataset.i18n); });
    for (const [attribute, dataKey] of [['placeholder', 'i18nPlaceholder'], ['aria-label', 'i18nAria'], ['title', 'i18nTitle']]) {
      document.querySelectorAll('[data-' + dataKey.replace(/[A-Z]/g, letter => '-' + letter.toLowerCase()) + ']')
        .forEach(node => node.setAttribute(attribute, t(node.dataset[dataKey])));
    }
    document.querySelectorAll('[data-language]').forEach(button => {
      const selected = button.dataset.language === language;
      button.classList.toggle('selected', selected);
      button.setAttribute('aria-pressed', String(selected));
    });
  }
  async function setLanguage(code) {
    if (!languages.includes(code)) return false;
    await load(code);
    language = code;
    try { localStorage.setItem('control-language', code); } catch {}
    apply();
    return true;
  }
  async function init() {
    await load('en');
    try { await setLanguage(preferred()); } catch { await setLanguage('en'); }
  }
  return {init, t, setLanguage, normalize, languages, get language() { return language; }, get locale() { return locales[language]; }};
})();
