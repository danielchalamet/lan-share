'use strict';
window.I18n = (() => {
  const languages = ['ru', 'en', 'fr', 'de', 'es'];
  let saved;
  try { saved = localStorage.getItem('lan-share-language'); } catch {}
  const preferred = (navigator.languages || [navigator.language]).map(code => code.toLowerCase().split('-')[0]);
  let language = languages.includes(saved) ? saved : preferred.find(code => languages.includes(code)) || 'en';
  let dictionaries = {};
  const canonical = value => {
    if (Object.hasOwn(dictionaries.en || {}, value)) return value;
    for (const dictionary of Object.values(dictionaries)) {
      for (const [key, text] of Object.entries(dictionary)) if (value === text) return key;
    }
    return value;
  };
  function t(key) { return dictionaries[language]?.[key] ?? dictionaries.en?.[key] ?? key; }
  function setText(element, source) {
    element.dataset.i18n = canonical(source);
    element.textContent = t(element.dataset.i18n);
  }
  function apply() {
    document.documentElement.lang = language;
    document.title = t('Экран рядом');
    document.querySelectorAll('[data-i18n]').forEach(element => { element.textContent = t(element.dataset.i18n); });
    for (const attribute of ['placeholder', 'aria-label']) {
      document.querySelectorAll(`[data-i18n-${attribute}]`).forEach(element => {
        element.setAttribute(attribute, t(element.getAttribute(`data-i18n-${attribute}`)));
      });
    }
    document.getElementById('language').value = language;
  }
  const ready = fetch('/locales.json').then(response => {
    if (!response.ok) throw new Error('Could not load translations. Reload the page.');
    return response.json();
  }).then(data => { dictionaries = data; apply(); });
  async function change(value) {
    await ready;
    if (!languages.includes(value)) return;
    language = value;
    try { localStorage.setItem('lan-share-language', value); } catch {}
    apply();
    window.dispatchEvent(new Event('languagechange'));
  }
  return { t, setText, change, ready, canonical, get language() { return language; } };
})();
