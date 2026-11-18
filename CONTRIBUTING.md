# Contributing

## Translations

Edit the UTF-8 JSON catalogs under web/locales/. Every language must contain the same keys as en.json. Keep named placeholders such as {name}, {mac}, {time} and {detail} unchanged. Translate the surrounding sentence freely.

Use plain text only. Templates are rendered with textContent or attribute setters; do not add HTML. User-defined names, addresses, real hostnames and vendor registry entries are not translated.

For new UI text, use t('key', parameters) in JavaScript or a data-i18n attribute in HTML. Use data-i18n-placeholder, data-i18n-aria and data-i18n-title for attributes. For engine messages use message('key', **parameters) and retain its metadata through error_message(error). Do not concatenate localized sentences or translate persistent access-rule values.

Python localizes each API response independently from X-Control-Language. The worker stores language-independent message keys and parameters. Driver/OS diagnostics keep their original text inside a translated explanation.

Run both test suites documented in the README. The catalog tests check keys, placeholders, source references, untranslated HTML, UTF-8 integrity and independent client languages. Browser-module tests cover selection, persistence, fallback, accessibility attributes and literal interpolation of user text.

## Testing changes

Prefer the demo network for development. Real network testing requires an appropriate Windows/Npcap setup and a network you administer. Do not commit runtime data, session tokens or packet captures.
