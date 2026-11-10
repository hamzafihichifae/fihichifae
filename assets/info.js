/* fihi-chifae info page: shows the visitor's language (same preference as the shop)
   and keeps #about, #faq... anchors working in every language. */
(function () {
  'use strict';
  var KEY = 'dhenbio_lang';
  var lang = 'ar';
  try { lang = localStorage.getItem(KEY) || 'ar'; } catch (e) { /* ignore */ }
  if (['ar', 'fr', 'en'].indexOf(lang) === -1) lang = 'ar';

  function apply(l) {
    lang = l;
    document.documentElement.lang = l;
    document.documentElement.dir = l === 'ar' ? 'rtl' : 'ltr';
    document.querySelectorAll('[data-lang-block]').forEach(function (a) { a.hidden = a.dataset.langBlock !== l; });
    document.querySelectorAll('.info-langs button').forEach(function (b) { b.classList.toggle('active', b.dataset.lang === l); });
    scrollToHash();
  }

  function scrollToHash() {
    var id = (window.location.hash || '').slice(1);
    if (!id) return;
    var block = document.querySelector('[data-lang-block="' + lang + '"]');
    var target = block && (block.querySelector('#' + CSS.escape(id)) || block.querySelector('[data-anchor="' + CSS.escape(id) + '"]'));
    if (target) target.scrollIntoView();
  }

  document.querySelectorAll('.info-langs button').forEach(function (b) {
    b.addEventListener('click', function () {
      try { localStorage.setItem(KEY, b.dataset.lang); } catch (e) { /* ignore */ }
      apply(b.dataset.lang);
    });
  });
  document.addEventListener('click', function (e) {
    var a = e.target.closest('nav.toc a');
    if (!a) return;
    e.preventDefault();
    history.replaceState(null, '', a.getAttribute('href'));
    scrollToHash();
  });
  window.addEventListener('hashchange', scrollToHash);
  apply(lang);

  // the shop number is set by the admin (profile panel): refresh every link
  fetch('/api/v1/settings').then(function (r) { return r.ok ? r.json() : null; }).then(function (st) {
    var d = st && String(st.whatsapp || '').replace(/\D/g, '');
    if (!d || d.length < 9) return;
    var text = d.indexOf('212') === 0 && d.length === 12
      ? '+212 ' + d.slice(3, 6) + ' ' + d.slice(6, 9) + ' ' + d.slice(9) : '+' + d;
    document.querySelectorAll('a[href^="https://wa.me/"]').forEach(function (a) { a.href = 'https://wa.me/' + d; });
    document.querySelectorAll('a[href^="tel:"]').forEach(function (a) { a.href = 'tel:+' + d; });
    document.querySelectorAll('[data-shop-phone]').forEach(function (el) { el.textContent = text; });
  }).catch(function () { /* keep the numbers written in the page */ });
})();
