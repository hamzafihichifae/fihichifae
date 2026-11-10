/* fihi-chifae : إدارة المنتجات والفئات والأرشيف عبر API v1 */
(function () {
  'use strict';

  const $ = (s, c) => (c || document).querySelector(s);
  const $$ = (s, c) => Array.from((c || document).querySelectorAll(s));
  const { apiJson, toast, esc, mad } = window.AdminAuth;

  const DEL_SVG = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6" stroke-linecap="round"/></svg>';
  const EDIT_SVG = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const X_SVG = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12" stroke-linecap="round"/></svg>';
  const FALLBACK_IMG = '/media/cat-default.svg';

  let CATS = [];
  let PRODUCTS = [];

  /* ---------------- helpers ---------------- */
  const normalize = (s) => String(s || '').trim().replace(/\s+/g, ' ').toLowerCase();
  const catTitle = (slug) => { const c = CATS.find((x) => x.id === slug); return c ? (c.title_ar || slug) : slug; };
  const findExactCategory = (name) => {
    const n = normalize(name);
    return CATS.find((c) => [c.title_ar, c.title_fr, c.title_en].some((t) => normalize(t) === n)) || null;
  };
  const filterCats = (q) => {
    const n = normalize(q);
    return n ? CATS.filter((c) => [c.title_ar, c.title_fr, c.title_en].some((t) => normalize(t).indexOf(n) !== -1)) : CATS.slice();
  };
  const fail = (e) => { if (e && e.status !== 401) toast(e.message || 'خطأ في الخادم', 'error'); };

  // Broken images (e.g. a deleted upload) fall back to the neutral category picture.
  document.addEventListener('error', (e) => {
    const img = e.target;
    if (img.tagName === 'IMG' && !img.dataset.fallback) { img.dataset.fallback = '1'; img.src = FALLBACK_IMG; }
  }, true);

  /* ---------------- category combobox (used by the new-product form and edit rows) ---------------- */
  function renderCombo(input, dd) {
    const q = input.value.trim();
    const items = filterCats(q);
    let html = items.map((c) =>
      '<button type="button" class="combo-item" data-title="' + esc(c.title_ar) + '">' + esc(c.title_ar) +
      (c.title_fr && c.title_fr !== c.title_ar ? '<small>' + esc(c.title_fr) + '</small>' : '') + '</button>').join('');
    if (q && !findExactCategory(q)) {
      html += q.length >= 2
        ? '<div class="combo-item create">+ ستُنشأ الفئة « ' + esc(q) + ' » عند الحفظ</div>'
        : '<div class="combo-empty">واصل الكتابة…</div>';
    }
    dd.innerHTML = html || '<div class="combo-empty">لا توجد فئات بعد — اكتب اسم فئة جديدة</div>';
    dd.hidden = false;
  }

  function bindCombo(input, dd) {
    input.addEventListener('input', () => renderCombo(input, dd));
    input.addEventListener('focus', () => renderCombo(input, dd));
    input.addEventListener('keydown', (e) => { if (e.key === 'Escape') dd.hidden = true; });
    dd.addEventListener('click', (e) => {
      const item = e.target.closest('[data-title]');
      if (item) { input.value = item.dataset.title; dd.hidden = true; input.focus(); }
    });
  }

  document.addEventListener('click', (e) => {
    $$('.combo-dropdown').forEach((dd) => {
      if (!dd.parentElement.contains(e.target)) dd.hidden = true;
    });
  });

  async function ensureCategory(name) {
    const exact = findExactCategory(name);
    if (exact) return exact.id;
    try {
      const data = await apiJson('/api/v1/categories', { method: 'POST', body: { name } });
      const c = data.category;
      CATS.push({ id: c.slug, title_ar: c.title_ar, title_fr: c.title_fr, title_en: c.title_en, img: c.img });
      return c.slug;
    } catch (e) {
      if (e.status === 409 && e.payload && e.payload.id) return e.payload.id;
      throw e;
    }
  }

  /* ---------------- sizes editor ---------------- */
  // value, label; a size always reads "<value> <unit>" (e.g. 250 g) whatever the language
  const UNITS = [['g', 'g · غرام'], ['kg', 'kg · كغ'], ['L', 'L · لتر']];
  function sizeRowHTML(s) {
    s = s || {};
    const unit = s.unit || 'kg';
    return '<div class="size-row" data-size-row>' +
      '<div class="sr-qty" dir="ltr">' +
      '<input type="text" class="input sm sr-size" value="' + esc(s.size != null ? s.size : '') + '" placeholder="250" inputmode="decimal" aria-label="الحجم" title="الحجم (مثال: 250)">' +
      '<select class="input sm sr-unit" aria-label="الوحدة">' + UNITS.map((u) =>
        '<option value="' + u[0] + '"' + (unit === u[0] ? ' selected' : '') + '>' + u[1] + '</option>').join('') + '</select>' +
      '</div>' +
      '<input type="number" class="input sm sr-price" value="' + esc(s.price != null ? s.price : '') + '" min="0" step="0.01" placeholder="السعر" aria-label="السعر">' +
      '<button type="button" class="icon-btn danger" data-del-size title="حذف الحجم" aria-label="حذف الحجم">' + X_SVG + '</button>' +
      '</div>';
  }

  function collectSizes(list) {
    const out = [];
    for (const row of $$('[data-size-row]', list)) {
      const size = $('.sr-size', row).value.trim();
      const price = $('.sr-price', row).value.trim();
      if (!size && !price) continue;
      if (!size) throw new Error('يرجى إدخال قيمة الحجم.');
      if (price === '' || isNaN(parseFloat(price)) || parseFloat(price) < 0) throw new Error('يرجى إدخال سعر صحيح لكل حجم.');
      out.push({ size, unit: $('.sr-unit', row).value, price: parseFloat(price) });
    }
    return out;
  }

  // one delegated handler for every sizes editor on the page
  document.addEventListener('click', (e) => {
    const add = e.target.closest('[data-add-size]');
    if (add) {
      const list = add.parentElement.querySelector('.sizes-list');
      list.insertAdjacentHTML('beforeend', sizeRowHTML(null));
      return;
    }
    const del = e.target.closest('[data-del-size]');
    if (del) {
      const list = del.closest('.sizes-list');
      const row = del.closest('[data-size-row]');
      if (list.children.length > 1) row.remove();
      else { $('.sr-size', row).value = ''; $('.sr-price', row).value = ''; }
    }
  });

  /* ---------------- images ---------------- */
  function readFile(file) {
    return new Promise((resolve, reject) => {
      if (!file) return resolve('');
      if (!/^image\/(png|jpeg|webp|gif)$/.test(file.type)) return reject(new Error('يجب أن تكون الصورة بصيغة PNG أو JPG أو WEBP أو GIF.'));
      if (file.size > 8 * 1024 * 1024) return reject(new Error('الصورة كبيرة جداً (الحد 8 ميغا).'));
      const r = new FileReader();
      r.onload = () => resolve(r.result);
      r.onerror = () => reject(new Error('تعذر قراءة الصورة.'));
      r.readAsDataURL(file);
    });
  }

  function previewImage() {
    const box = $('#imgPreview');
    const file = $('#fFile').files[0];
    if (!file) { box.textContent = 'لا توجد صورة'; return; }
    readFile(file).then((src) => { box.innerHTML = '<img alt="معاينة">'; box.firstChild.src = src; })
      .catch((e) => { toast(e.message, 'error'); $('#fFile').value = ''; box.textContent = 'لا توجد صورة'; });
  }

  /* ---------------- load + render ---------------- */
  async function loadAll() {
    let data;
    try {
      data = await apiJson('/api/v1/catalog');
    } catch (e) {
      $('#productList').innerHTML = '<p class="empty">تعذر تحميل المنتجات.</p>';
      $('#catList').innerHTML = '<p class="empty">تعذر تحميل الفئات.</p>';
      fail(e);
      return;
    }
    CATS = (data.categories || []).map((c) => ({ id: c.id, title_ar: c.title_ar, title_fr: c.title_fr, title_en: c.title_en, img: c.img, count: (c.products || []).length }));
    PRODUCTS = [];
    (data.categories || []).forEach((c) => (c.products || []).forEach((p) => PRODUCTS.push(Object.assign({}, p, { cat: c.id, img: p.img || c.img }))));
    renderCategories();
    renderProducts();
    loadArchive();
  }

  function renderCategories() {
    const box = $('#catList');
    if (!CATS.length) { box.innerHTML = '<p class="empty">لا توجد فئات. أضف منتجاً لإنشاء أول فئة.</p>'; return; }
    box.innerHTML = CATS.map((c) =>
      '<div class="row"><div class="row-view">' +
      '<img src="' + esc(c.img || FALLBACK_IMG) + '" alt="">' +
      '<div class="info"><b>' + esc(c.title_ar || c.id) + '</b><span class="meta">' + c.count + ' منتج</span></div>' +
      '<button type="button" class="icon-btn danger" data-del-cat="' + esc(c.id) + '" title="حذف الفئة (أرشفة)" aria-label="حذف الفئة">' + DEL_SVG + '</button>' +
      '</div></div>').join('');
  }

  function sizeTags(p) {
    if (!p.sizes || !p.sizes.length) return '<span class="meta">السعر عند الطلب</span>';
    return '<div class="size-tags">' + p.sizes.map((s) =>
      '<span class="size-tag" dir="ltr">' + esc(s.size) + ' ' + esc(s.unit) + ' · ' + mad(s.price) + '</span>').join('') + '</div>';
  }

  function productRowHTML(p) {
    const sizes = p.sizes_custom ? p.sizes : [];
    return '<div class="row" data-id="' + esc(p.id) + '">' +
      '<div class="row-view">' +
      '  <img src="' + esc(p.img || FALLBACK_IMG) + '" alt="">' +
      '  <div class="info"><b>' + esc(p.name) + '</b><span class="meta">' + esc(catTitle(p.cat)) + '</span>' + sizeTags(p) + '</div>' +
      '  <button type="button" class="icon-btn edit" data-edit title="تعديل" aria-label="تعديل">' + EDIT_SVG + '</button>' +
      '  <button type="button" class="icon-btn danger" data-del title="حذف (ينقل إلى الأرشيف)" aria-label="حذف">' + DEL_SVG + '</button>' +
      '</div>' +
      '<div class="row-edit">' +
      '  <div class="edit-grid">' +
      '    <div class="field"><label>اسم المنتج</label><input type="text" class="input sm e-name" maxlength="80" value="' + esc(p.name) + '"></div>' +
      '    <div class="field"><label>الفئة</label><div class="cat-combo"><input type="text" class="input sm e-cat" autocomplete="off" maxlength="60" value="' + esc(catTitle(p.cat)) + '"><div class="combo-dropdown" hidden></div></div></div>' +
      '    <div class="field"><label>سعر 1 كغ / 1 ل</label><input type="number" class="input sm e-price" min="0" step="0.01" value="' + esc(p.sizes_custom ? '' : (p.min != null ? p.min : '')) + '" placeholder="' + (p.sizes_custom ? 'محدد بالأحجام أسفله' : '') + '"></div>' +
      '    <div class="field"><label>صورة جديدة (اختياري)</label><input type="file" class="input sm e-file" accept="image/png,image/jpeg,image/webp,image/gif"></div>' +
      '    <div class="field"><label>الاسم بالفرنسية (للبحث)</label><input type="text" class="input sm e-name-fr" maxlength="80" dir="ltr" value="' + esc(p.name_fr || '') + '"></div>' +
      '    <div class="field"><label>الاسم بالإنجليزية (للبحث)</label><input type="text" class="input sm e-name-en" maxlength="80" dir="ltr" value="' + esc(p.name_en || '') + '"></div>' +
      '  </div>' +
      '  <div class="field"><label>الوصف</label><textarea class="input e-desc" maxlength="2000" placeholder="الأصل، طريقة الاستعمال، المميزات…">' + esc(p.description || '') + '</textarea></div>' +
      '  <div class="sizes-box"><div class="sizes-list">' + (sizes.length ? sizes.map(sizeRowHTML).join('') : sizeRowHTML(null)) + '</div>' +
      '    <button type="button" class="btn-soft sm" data-add-size>+ إضافة حجم</button>' +
      '    <p class="hint" style="margin-top:.4rem">بدون أحجام = الأحجام الافتراضية محسوبة من السعر.</p></div>' +
      '  <div class="edit-actions"><button type="button" class="btn-primary sm" data-save>حفظ</button><button type="button" class="btn-soft sm" data-cancel>إلغاء</button></div>' +
      '</div>' +
      '</div>';
  }

  function renderProducts() {
    const box = $('#productList');
    if (!PRODUCTS.length) { box.innerHTML = '<p class="empty">لا يوجد منتج في الكتالوج.</p>'; return; }
    box.innerHTML = PRODUCTS.map(productRowHTML).join('');
    $$('.row', box).forEach((row) => bindCombo($('.e-cat', row), $('.combo-dropdown', row)));
  }

  async function loadArchive() {
    const box = $('#archiveList');
    try {
      const data = await apiJson('/api/v1/archive');
      const prods = data.products || [], cats = data.categories || [];
      if (!prods.length && !cats.length) { box.innerHTML = '<p class="empty">الأرشيف فارغ.</p>'; return; }
      box.innerHTML =
        prods.map((p) =>
          '<div class="row"><div class="row-view">' +
          '<img src="' + esc(p.img || FALLBACK_IMG) + '" alt="">' +
          '<div class="info"><b>' + esc(p.name) + '</b><span class="archived-at">منتج · حُذف ' + esc(String(p.revoked_at || '').slice(0, 16).replace('T', ' ')) + '</span></div>' +
          '<button type="button" class="btn-soft sm" data-restore="' + esc(p.id) + '">استرجاع</button>' +
          '</div></div>').join('') +
        cats.map((c) =>
          '<div class="row"><div class="row-view"><div class="info"><b>' + esc(c.title_ar) + '</b>' +
          '<span class="archived-at">فئة · حُذفت ' + esc(String(c.archived_at || '').slice(0, 16).replace('T', ' ')) + ' (تُسترجع تلقائياً مع منتجاتها)</span></div></div></div>').join('');
    } catch (e) {
      box.innerHTML = '<p class="empty">تعذر تحميل الأرشيف.</p>';
    }
  }

  /* ---------------- actions ---------------- */
  async function submitProduct(e) {
    e.preventDefault();
    const name = $('#fName').value.trim();
    const catInput = $('#fCat').value.trim();
    const priceRaw = $('#fPrice').value.trim();
    const price = priceRaw === '' ? null : parseFloat(priceRaw);
    if (!catInput || catInput.length < 2) { toast('يرجى إدخال الفئة (حرفان على الأقل).', 'error'); $('#fCat').focus(); return; }
    if (!name) { toast('يرجى إدخال اسم المنتج.', 'error'); $('#fName').focus(); return; }
    let sizes;
    try { sizes = collectSizes($('#sizesList')); } catch (err) { toast(err.message, 'error'); return; }
    if (!sizes.length && (price === null || isNaN(price) || price < 0)) { toast('يرجى إدخال السعر أو الأحجام.', 'error'); $('#fPrice').focus(); return; }

    const btn = $('#btnSubmit');
    btn.disabled = true;
    try {
      const img = await readFile($('#fFile').files[0]);
      const cat = await ensureCategory(catInput);
      const body = { name, cat, img, sizes, description: $('#fDesc').value.trim(),
        name_fr: $('#fNameFr').value.trim(), name_en: $('#fNameEn').value.trim() };
      if (price !== null && !isNaN(price)) body.price = price;
      await apiJson('/api/v1/products', { method: 'POST', body });
      toast('تمت إضافة « ' + name + ' » إلى « ' + catTitle(cat) + ' ».');
      $('#productForm').reset();
      $('#sizesList').innerHTML = sizeRowHTML(null);
      $('#imgPreview').textContent = 'لا توجد صورة';
      await loadAll();
    } catch (err) {
      fail(err);
    } finally {
      btn.disabled = false;
    }
  }

  async function saveEdit(row) {
    const id = row.dataset.id;
    const name = $('.e-name', row).value.trim();
    const catInput = $('.e-cat', row).value.trim();
    const priceRaw = $('.e-price', row).value.trim();
    if (!name) { toast('يرجى إدخال اسم المنتج.', 'error'); return; }
    if (!catInput) { toast('يرجى إدخال الفئة.', 'error'); return; }
    let sizes;
    try { sizes = collectSizes($('.sizes-list', row)); } catch (err) { toast(err.message, 'error'); return; }
    if (!sizes.length && (priceRaw === '' || isNaN(parseFloat(priceRaw)) || parseFloat(priceRaw) < 0)) {
      toast('يرجى إدخال السعر أو الأحجام.', 'error'); return;
    }
    const btn = $('[data-save]', row);
    btn.disabled = true;
    try {
      const img = await readFile($('.e-file', row).files[0]);
      const cat = await ensureCategory(catInput);
      const body = { name, cat, sizes, price: priceRaw === '' ? '' : parseFloat(priceRaw), description: $('.e-desc', row).value.trim(),
        name_fr: $('.e-name-fr', row).value.trim(), name_en: $('.e-name-en', row).value.trim() };
      if (img) body.img = img;
      await apiJson('/api/v1/products/' + encodeURIComponent(id), { method: 'PUT', body });
      toast('تم تحديث المنتج.');
      await loadAll();
    } catch (err) {
      fail(err);
      btn.disabled = false;
    }
  }

  async function onListClick(e) {
    const row = e.target.closest('.row');
    if (e.target.closest('[data-edit]')) { row.classList.add('editing'); $('.e-name', row).focus(); return; }
    if (e.target.closest('[data-cancel]')) { renderProducts(); return; }
    if (e.target.closest('[data-save]')) { saveEdit(row); return; }
    if (e.target.closest('[data-del]')) {
      const p = PRODUCTS.find((x) => x.id === row.dataset.id);
      if (!(await AdminAuth.confirm('حذف « ' + (p ? p.name : '') + ' » من المتجر؟ سيُنقل إلى الأرشيف ويمكن استرجاعه لاحقاً.', 'حذف', true))) return;
      try {
        await apiJson('/api/v1/products/' + encodeURIComponent(row.dataset.id), { method: 'DELETE' });
        toast('تم حذف المنتج ونقله إلى الأرشيف.');
        await loadAll();
      } catch (err) { fail(err); }
    }
  }

  async function onCatClick(e) {
    const btn = e.target.closest('[data-del-cat]');
    if (!btn) return;
    const c = CATS.find((x) => x.id === btn.dataset.delCat);
    if (c && c.count) { toast('لا يمكن حذف فئة تحتوي على منتجات — احذف منتجاتها أولاً.', 'error'); return; }
    if (!(await AdminAuth.confirm('حذف الفئة « ' + (c ? c.title_ar : '') + ' »؟ ستُنقل إلى الأرشيف.', 'حذف', true))) return;
    try {
      await apiJson('/api/v1/categories/' + encodeURIComponent(btn.dataset.delCat), { method: 'DELETE' });
      toast('تم حذف الفئة ونقلها إلى الأرشيف.');
      await loadAll();
    } catch (err) { fail(err); }
  }

  async function onArchiveClick(e) {
    const btn = e.target.closest('[data-restore]');
    if (!btn) return;
    btn.disabled = true;
    try {
      await apiJson('/api/v1/archive/products/' + encodeURIComponent(btn.dataset.restore) + '/restore', { method: 'POST' });
      toast('تم استرجاع المنتج إلى المتجر.');
      await loadAll();
    } catch (err) { fail(err); btn.disabled = false; }
  }

  /* ---------------- init (listeners bound exactly once) ---------------- */
  function init() {
    $('#sizesList').innerHTML = sizeRowHTML(null);
    bindCombo($('#fCat'), $('#catDropdown'));
    $('#fFile').addEventListener('change', previewImage);
    $('#productForm').addEventListener('submit', submitProduct);
    $('#productList').addEventListener('click', onListClick);
    $('#catList').addEventListener('click', onCatClick);
    $('#archiveList').addEventListener('click', onArchiveClick);
    loadAll();
  }

  document.addEventListener('DOMContentLoaded', () => AdminAuth.require(init));
})();
