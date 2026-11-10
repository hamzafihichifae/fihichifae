/* فيه شفاء - لوحة التحكم: مؤشرات، رسوم بيانية، تصدير Excel، تأكيد/رفض الطلبات، طلب يدوي */
(function () {
  'use strict';

  const $ = (s, c) => (c || document).querySelector(s);
  const $$ = (s, c) => Array.from((c || document).querySelectorAll(s));
  const { apiJson, toast, esc, mad } = window.AdminAuth;
  const GREEN = ['#16A34A', '#4AAA6F', '#7EC79B', '#0E5E2D', '#229D4E', '#B8E0C8', '#12843D', '#0B4523'];

  let charts = [];
  let catNames = {};
  let orders = [];
  let statusFilter = 'all';
  let catalog = { categories: [], products: [] };

  /* ---------------- helpers ---------------- */
  const pad = (n) => String(n).padStart(2, '0');
  function today() { const d = new Date(); return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); }
  function currentMonthBounds() {
    const d = new Date();
    const y = d.getFullYear(), m = d.getMonth();
    return { from: y + '-' + pad(m + 1) + '-01', to: y + '-' + pad(m + 1) + '-' + pad(new Date(y, m + 1, 0).getDate()) };
  }
  function monthLabel(ym) {
    const [y, m] = String(ym).split('-').map(Number);
    if (!y || !m) return ym;
    return new Date(y, m - 1, 1).toLocaleDateString('ar-MA', { month: 'long', year: 'numeric' });
  }
  function fmtDate(ts) { return String(ts || '').slice(0, 16).replace('T', ' '); }
  const catLabel = (slug) => catNames[slug] || slug || '—';
  function waNumber(phone) {
    let d = String(phone || '').replace(/\D/g, '');
    if (d.startsWith('00')) d = d.slice(2);
    if (d.startsWith('0')) d = '212' + d.slice(1);
    return d.length >= 9 ? d : '';
  }
  function safeUrl(u) { return /^https?:\/\//i.test(String(u || '')) ? String(u) : ''; }
  // stored size id "250g" is shown as "250 g" (value then unit, in every language)
  const sizeText = (s) => String(s || '').replace(/^([\d.,]+)\s*(g|kg|L)$/i, '$1 $2');

  function whenChart(cb) {
    if (window.Chart) return cb();
    window.addEventListener('load', function () { if (window.Chart) cb(); });
  }

  /* ---------------- summary + charts ---------------- */
  async function loadSummary() {
    let data;
    try {
      data = await apiJson('/api/v1/sales/summary');
    } catch (e) {
      if (e.status !== 401) toast('تعذر تحميل المؤشرات: ' + e.message, 'error');
      return;
    }
    catNames = data.categoryNames || {};
    const t = data.totals || {}, m = data.month || {}, p = data.pending || {};
    $('#kRevenue').textContent = mad(t.revenue);
    $('#kRevenueSub').textContent = t.orders + ' طلب مؤكد · منها توصيل ' + mad(t.delivery);
    $('#kMonthRevenue').textContent = mad(m.revenue);
    $('#kMonthSub').textContent = m.orders + ' طلب · ' + m.units + ' وحدة (' + monthLabel(m.label) + ')';
    $('#kPending').textContent = String(p.orders || 0);
    $('#kPendingSub').textContent = p.orders ? 'بقيمة ' + mad(p.amount) + ' — غير محتسبة في الإيرادات' : 'لا توجد طلبات معلقة';
    $('#kPendingCard').classList.toggle('attention', !!p.orders);
    $('#kUnits').textContent = String(t.units || 0);
    $('#kUnitsSub').textContent = m.units + ' هذا الشهر · ' + (data.subscribers || 0) + ' مشترك في النشرة';

    fillMonthSelector(data.months || [], (data.revenueByMonth || []).map((r) => r.ym));
    whenChart(() => renderCharts(data.revenueByMonth || [], data.topSellers || [], data.byCategory || []));
  }

  function fillMonthSelector(withSales, recent) {
    const sel = $('#monthSel');
    const prev = sel.value;
    const all = Array.from(new Set([...recent, ...withSales])).sort().reverse();
    sel.innerHTML = '<option value="">كل الأشهر</option>' +
      all.map((ym) => '<option value="' + esc(ym) + '">' + esc(monthLabel(ym)) + '</option>').join('');
    const cur = today().slice(0, 7);
    sel.value = prev && all.includes(prev) ? prev : (all.includes(cur) ? cur : '');
  }

  function chartBox(id) {
    let canvas = document.getElementById(id);
    const box = canvas ? canvas.closest('.chart-box') : null;
    return { canvas, box };
  }

  function renderCharts(byMonth, top, byCat) {
    charts.forEach((c) => c.destroy());
    charts = [];
    const font = { family: 'Cairo' };
    const make = (id, conf) => {
      const { canvas, box } = chartBox(id);
      if (!box) return;
      const hasData = conf.data.some((v) => Number(v) > 0);
      let empty = box.querySelector('.empty');
      if (!hasData) {
        canvas.hidden = true;
        if (!empty) { empty = document.createElement('p'); empty.className = 'empty'; box.appendChild(empty); }
        empty.textContent = conf.emptyText || 'لا توجد مبيعات مؤكدة بعد.';
        return;
      }
      canvas.hidden = false;
      if (empty) empty.remove();
      charts.push(new Chart(canvas, {
        type: conf.type,
        data: { labels: conf.labels, datasets: [{ label: 'الإيرادات (د.م.)', data: conf.data, backgroundColor: conf.colors, borderColor: conf.type === 'doughnut' ? '#fff' : conf.colors, borderWidth: conf.type === 'doughnut' ? 2 : 0, borderRadius: conf.type === 'bar' ? 6 : 0 }] },
        options: {
          responsive: true, maintainAspectRatio: false, indexAxis: conf.indexAxis || 'x', locale: 'en-US',
          plugins: {
            legend: { display: conf.type === 'doughnut', position: 'bottom', rtl: true, labels: { font } },
            tooltip: { rtl: true, callbacks: { label: (ctx) => ' ' + mad(ctx.raw) } },
          },
          scales: conf.type === 'doughnut' ? {} : {
            x: { grid: { display: conf.indexAxis === 'y' }, ticks: { font }, beginAtZero: true },
            y: { grid: { color: '#EEF4EF', display: conf.indexAxis !== 'y' }, ticks: { font }, beginAtZero: true },
          },
        },
      }));
    };
    make('chartRevenue', { type: 'bar', labels: byMonth.map((r) => monthLabel(r.ym)), data: byMonth.map((r) => r.revenue), colors: '#16A34A' });
    make('chartTop', { type: 'bar', indexAxis: 'y', labels: top.map((r) => r.name), data: top.map((r) => r.revenue), colors: '#0E5E2D' });
    make('chartCat', { type: 'doughnut', labels: byCat.map((c) => catLabel(c.label)), data: byCat.map((c) => c.revenue), colors: GREEN });
  }

  /* ---------------- orders ---------------- */
  let customer = '';   // active customer filter ('' = everyone)
  let allTime = false; // that customer's whole history instead of the date range
  let ordersSeq = 0;   // ignore answers of superseded requests

  async function loadOrders() {
    const from = $('#ordersFrom').value, to = $('#ordersTo').value;
    const b = currentMonthBounds();
    const period = from === b.from && to === b.to ? 'هذا الشهر'
      : (from ? 'من ' + from : '') + (to ? ' إلى ' + to : '');
    $('#ordersTitle').textContent = customer
      ? (allTime ? 'كل طلبات « ' + customer + ' »' : 'طلبات « ' + customer + ' » · ' + period)
      : (period === 'هذا الشهر' ? 'طلبات هذا الشهر' : 'الطلبات ' + period);
    const qs = new URLSearchParams();
    if (customer) qs.set('buyer', customer);
    if (customer && allTime) qs.set('all', '1');
    else {
      if (from) qs.set('from', from);
      if (to) qs.set('to', to);
    }
    const seq = ++ordersSeq;
    let data;
    try {
      data = await apiJson('/api/v1/orders?' + qs.toString());
    } catch (e) {
      if (e.status !== 401 && seq === ordersSeq) $('#ordersList').innerHTML = '<p class="empty">' + esc(e.message) + '</p>';
      return;
    }
    if (seq !== ordersSeq) return;
    orders = data.orders || [];
    renderCustomerSummary(customer && allTime ? data.customer : null);
    renderOrders();
  }

  function renderCustomerSummary(c) {
    const box = $('#customerSummary');
    if (!c) { box.hidden = true; box.innerHTML = ''; return; }
    const item = (label, value, cls) => '<div class="cs-item' + (cls ? ' ' + cls : '') + '"><span>' + label + '</span><b>' + esc(value) + '</b></div>';
    box.innerHTML =
      item('الزبون', c.buyer, 'cs-name') +
      item('عدد الطلبات', c.orders + (c.orders === c.confirmed ? '' : ' (' + c.confirmed + ' مؤكد)')) +
      item('أول طلب', c.first_order ? fmtDate(c.first_order).slice(0, 10) : '—') +
      item('آخر طلب', c.last_order ? fmtDate(c.last_order).slice(0, 10) : '—') +
      item('مجموع المؤكد', mad(c.confirmed_total));
    box.hidden = false;
  }

  /* customer filter: suggestions while typing, applied on pick / Enter */
  let suggestTimer = 0;
  function suggestCustomers() {
    clearTimeout(suggestTimer);
    suggestTimer = setTimeout(async () => {
      const q = $('#customerFilter').value.trim();
      try {
        const data = await apiJson('/api/v1/orders/customers?q=' + encodeURIComponent(q));
        $('#customerList').innerHTML = (data.customers || []).map((c) =>
          '<option value="' + esc(c.buyer) + '" label="' + esc((c.phone ? c.phone + ' · ' : '') + c.orders + ' طلب') + '"></option>').join('');
      } catch (e) { /* suggestions are optional */ }
    }, 200);
  }

  function applyCustomer() {
    const value = $('#customerFilter').value.trim();
    if (value === customer) return;
    customer = value;
    if (!customer) allTime = false;
    syncCustomerControls();
    loadOrders();
  }

  function syncCustomerControls() {
    $('#customerAllTime').disabled = !customer;
    $('#customerAllTime').checked = allTime;
    $('#customerClear').hidden = !customer;
    $('#ordersFrom').disabled = $('#ordersTo').disabled = $('#ordersResetBtn').disabled = !!(customer && allTime);
  }

  function initCustomerFilter() {
    const input = $('#customerFilter');
    input.addEventListener('input', () => { suggestCustomers(); if (!input.value.trim()) applyCustomer(); });
    input.addEventListener('focus', suggestCustomers);
    input.addEventListener('change', applyCustomer);
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); applyCustomer(); } });
    $('#customerAllTime').addEventListener('change', (e) => { allTime = e.target.checked; syncCustomerControls(); loadOrders(); });
    $('#customerClear').addEventListener('click', () => { input.value = ''; allTime = false; applyCustomer(); });
    syncCustomerControls();
  }

  function renderOrders() {
    const pending = orders.filter((o) => o.status === 'pending');
    const confirmed = orders.filter((o) => o.status === 'confirmed');
    $('#nAll').textContent = orders.length;
    $('#nPending').textContent = pending.length;
    $('#nConfirmed').textContent = confirmed.length;
    const list = statusFilter === 'pending' ? pending : statusFilter === 'confirmed' ? confirmed : orders;

    const box = $('#ordersList');
    if (!list.length) {
      box.innerHTML = '<p class="empty">' + (customer ? 'لا توجد طلبات لهذا الزبون في هذه الفترة.' : 'لا توجد طلبات في هذه الفترة.') + '</p>';
    } else {
      box.innerHTML = list.map(orderHTML).join('');
    }
    const confirmedTotal = confirmed.reduce((s, o) => s + o.total, 0);
    const pendingTotal = pending.reduce((s, o) => s + o.total, 0);
    $('#ordersSummary').textContent = confirmed.length + ' مؤكد بقيمة ' + mad(confirmedTotal) +
      ' · ' + pending.length + ' بانتظار التأكيد بقيمة ' + mad(pendingTotal);
  }

  function orderHTML(o) {
    const isPending = o.status === 'pending';
    const wa = waNumber(o.phone);
    const loc = safeUrl(o.location);
    const phone = o.phone
      ? '<a class="chip" dir="ltr" href="tel:' + esc(o.phone.replace(/[^\d+]/g, '')) + '">' + esc(o.phone) + '</a>' : '';
    const waLink = wa
      ? '<a class="chip" href="https://wa.me/' + wa + '" target="_blank" rel="noopener">واتساب</a>' : '';
    const addr = (o.address || o.city || loc)
      ? '<div class="order-addr">' +
        (o.city ? '<span><b>المدينة:</b> ' + esc(o.city) + '</span>' : '') +
        (o.address ? '<span><b>العنوان:</b> ' + esc(o.address) + '</span>' : '') +
        (loc ? '<span><a href="' + esc(loc) + '" target="_blank" rel="noopener noreferrer">فتح الموقع على الخريطة</a></span>' : '') +
        '</div>'
      : '';
    const rows = o.items.map((it) =>
      '<tr><td>' + esc(it.product_name) + (it.size ? ' <span class="chip" dir="ltr">' + esc(sizeText(it.size)) + '</span>' : '') + '</td>' +
      '<td><span class="cat-tag">' + esc(catLabel(it.cat)) + '</span></td>' +
      '<td class="num">' + mad(it.price) + ' × ' + Number(it.qty) + '</td>' +
      '<td class="num"><b>' + mad((Number(it.price) || 0) * (Number(it.qty) || 0)) + '</b></td></tr>'
    ).join('');
    const sourceLabel = o.source === 'manual' ? 'يدوي' : o.source === 'chatbot' ? 'المساعد' : 'المتجر';
    const date = o.status === 'confirmed'
      ? 'أُكّد: ' + fmtDate(o.confirmed_at) + (o.source !== 'manual' ? ' · طُلب: ' + fmtDate(o.created) : '')
      : 'طُلب: ' + fmtDate(o.created);
    return (
      '<article class="order ' + esc(o.status) + '" data-oid="' + esc(o.id) + '">' +
      '  <div class="order-head">' +
      '    <span class="buyer">' + esc(o.buyer || 'بدون اسم') + '</span>' + phone + waLink +
      '    <span class="status ' + esc(o.status) + '">' + (isPending ? 'بانتظار التأكيد' : 'مؤكد') + '</span>' +
      '    <span class="source">' + sourceLabel + '</span>' +
      '    <span class="order-date">' + esc(date) + '</span>' +
      '  </div>' + addr +
      '  <div class="table-wrap"><table class="items"><thead><tr><th>المنتج</th><th>الفئة</th><th>السعر × الكمية</th><th>المجموع</th></tr></thead><tbody>' + rows + '</tbody></table></div>' +
      '  <div class="order-foot">' +
      '    <div class="totals"><span>المنتجات: <b class="num">' + mad(o.subtotal) + '</b></span>' +
      '      <span>التوصيل: <b class="num">' + (o.delivery_fee ? mad(o.delivery_fee) : 'مجاني') + '</b></span>' +
      '      <span class="grand">المجموع: <b class="num">' + mad(o.total) + '</b></span></div>' +
      (isPending
        ? '<div class="order-actions"><button type="button" class="btn-primary sm" data-action="confirm">تأكيد الطلب</button>' +
          '<button type="button" class="btn-danger" data-action="reject">رفض وحذف</button></div>'
        : '') +
      '  </div>' +
      '</article>'
    );
  }

  async function onOrderAction(e) {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const card = btn.closest('.order');
    const oid = card.dataset.oid;
    const order = orders.find((o) => o.id === oid);
    const isConfirm = btn.dataset.action === 'confirm';
    const ok = await AdminAuth.confirm(
      isConfirm
        ? 'تأكيد طلب « ' + (order ? order.buyer : '') + ' » بقيمة ' + mad(order ? order.total : 0) + '؟ سيُحتسب في إيرادات هذا الشهر.'
        : 'رفض طلب « ' + (order ? order.buyer : '') + ' »؟ سيتم حذفه نهائياً.',
      isConfirm ? 'تأكيد الطلب' : 'رفض وحذف',
      !isConfirm
    );
    if (!ok) return;
    $$('button', card).forEach((b) => { b.disabled = true; });
    try {
      await apiJson('/api/v1/orders/' + encodeURIComponent(oid) + '/' + btn.dataset.action, { method: 'POST' });
      toast(isConfirm ? 'تم تأكيد الطلب.' : 'تم رفض الطلب وحذفه.');
      await Promise.all([loadSummary(), loadOrders()]);
    } catch (err) {
      if (err.status !== 401) toast(err.message, 'error');
      $$('button', card).forEach((b) => { b.disabled = false; });
    }
  }

  /* ---------------- manual order ---------------- */
  async function loadCatalogForOrders() {
    try {
      const data = await apiJson('/api/v1/catalog');
      if (window.Delivery) Delivery.configure(data.settings);
      catalog.categories = (data.categories || []).map((c) => ({ slug: c.id, title: c.title_ar || c.id }));
      catalog.products = [];
      (data.categories || []).forEach((c) => (c.products || []).forEach((p) => {
        const first = (p.sizes || [])[0];
        catalog.products.push({ id: p.id, name: p.name, cat: c.id, price: first ? Number(first.price) : p.min });
      }));
      $('#productList').innerHTML = catalog.products.map((p) => '<option value="' + esc(p.name) + '"></option>').join('');
    } catch (e) { /* the form still works with typed products */ }
  }

  function catOptions(selected) {
    return '<option value="">اختر الفئة</option>' + catalog.categories.map((c) =>
      '<option value="' + esc(c.slug) + '"' + (c.slug === selected ? ' selected' : '') + '>' + esc(c.title) + '</option>').join('');
  }

  function addItemRow() {
    const row = document.createElement('div');
    row.className = 'mo-item';
    row.innerHTML =
      '<input type="text" class="input sm mo-name" list="productList" placeholder="اسم المنتج" aria-label="اسم المنتج" maxlength="80">' +
      '<select class="input sm mo-cat" aria-label="الفئة">' + catOptions('') + '</select>' +
      '<input type="number" class="input sm mo-price" min="0" step="0.01" placeholder="السعر" aria-label="السعر">' +
      '<input type="number" class="input sm mo-qty" min="1" step="1" value="1" aria-label="الكمية">' +
      '<button type="button" class="icon-btn danger mo-del" title="حذف" aria-label="حذف المنتج">' +
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12" stroke-linecap="round"/></svg></button>';
    $('#moItems').appendChild(row);
    return row;
  }

  function updateTotals() {
    let subtotal = 0;
    $$('.mo-item').forEach((row) => {
      subtotal += (parseFloat($('.mo-price', row).value) || 0) * (parseInt($('.mo-qty', row).value, 10) || 0);
    });
    const fee = window.Delivery ? Delivery.fee(subtotal, $('#moCity').value) : 0;
    $('#moSubtotal').textContent = mad(subtotal);
    $('#moFee').textContent = fee ? mad(fee) : 'مجاني';
    $('#moTotal').textContent = mad(subtotal + fee);
  }

  function openModal() {
    $('#manualOrderForm').reset();
    $('#moItems').innerHTML = '';
    addItemRow();
    updateTotals();
    $('#manualOrderModal').hidden = false;
    document.body.style.overflow = 'hidden';
    setTimeout(() => $('#moBuyer').focus(), 30);
  }

  function closeModal() {
    $('#manualOrderModal').hidden = true;
    document.body.style.overflow = '';
  }

  async function submitManualOrder(e) {
    e.preventDefault();
    const buyer = $('#moBuyer').value.trim();
    if (!buyer) { toast('اسم الزبون مطلوب.', 'error'); $('#moBuyer').focus(); return; }
    const items = [];
    for (const row of $$('.mo-item')) {
      const name = $('.mo-name', row).value.trim();
      const price = parseFloat($('.mo-price', row).value);
      const qty = parseInt($('.mo-qty', row).value, 10);
      const cat = $('.mo-cat', row).value;
      if (!name && isNaN(price)) continue; // empty line
      if (!name) { toast('اسم المنتج مطلوب.', 'error'); $('.mo-name', row).focus(); return; }
      if (!cat) { toast('يرجى اختيار فئة « ' + name + ' ».', 'error'); $('.mo-cat', row).focus(); return; }
      if (isNaN(price) || price < 0) { toast('سعر « ' + name + ' » غير صالح.', 'error'); $('.mo-price', row).focus(); return; }
      if (isNaN(qty) || qty < 1) { toast('كمية « ' + name + ' » غير صالحة.', 'error'); $('.mo-qty', row).focus(); return; }
      const known = catalog.products.find((p) => p.name === name && p.cat === cat);
      items.push({ id: known ? known.id : '', name, cat, price, qty });
    }
    if (!items.length) { toast('أضف منتجاً واحداً على الأقل.', 'error'); return; }

    const btn = $('#btnModalSubmit');
    btn.disabled = true;
    try {
      await apiJson('/api/v1/admin/orders', {
        method: 'POST',
        body: {
          buyer,
          phone: $('#moPhone').value.trim(),
          address: $('#moAddress').value.trim(),
          city: $('#moCity').value.trim(),
          location: $('#moLocation').value.trim(),
          items,
        },
      });
      closeModal();
      toast('تم حفظ الطلب اليدوي.');
      await Promise.all([loadSummary(), loadOrders()]);
    } catch (err) {
      if (err.status !== 401) toast(err.message, 'error');
    } finally {
      btn.disabled = false;
    }
  }

  function initManualOrder() {
    $('#btnAddManualOrder').addEventListener('click', openModal);
    $('#modalClose').addEventListener('click', closeModal);
    $('#btnModalCancel').addEventListener('click', closeModal);
    $('#manualOrderModal').addEventListener('click', (e) => { if (e.target.id === 'manualOrderModal') closeModal(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('#manualOrderModal').hidden) closeModal(); });
    $('#btnAddOrderItem').addEventListener('click', () => { $('.mo-name', addItemRow()).focus(); });
    $('#manualOrderForm').addEventListener('submit', submitManualOrder);
    $('#moCity').addEventListener('input', updateTotals);
    const items = $('#moItems');
    items.addEventListener('input', (e) => {
      if (e.target.classList.contains('mo-name')) {
        const row = e.target.closest('.mo-item');
        const p = catalog.products.find((x) => x.name === e.target.value.trim());
        if (p) {
          $('.mo-cat', row).value = p.cat;
          if (p.price != null && $('.mo-price', row).value === '') $('.mo-price', row).value = p.price;
        }
      }
      updateTotals();
    });
    items.addEventListener('change', updateTotals);
    items.addEventListener('click', (e) => {
      const del = e.target.closest('.mo-del');
      if (!del) return;
      if ($$('.mo-item').length > 1) del.closest('.mo-item').remove();
      else { $('#manualOrderForm').querySelectorAll('.mo-item input').forEach((i) => { i.value = i.classList.contains('mo-qty') ? '1' : ''; }); }
      updateTotals();
    });
  }

  /* ---------------- export ---------------- */
  async function download(url, btn, fallbackName, errorText) {
    btn.disabled = true;
    try {
      const res = await AdminAuth.api(url);
      if (!res.ok) throw new Error('api');
      const blob = await res.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = (res.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/)?.[1] || fallbackName;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 3000);
    } catch (e) {
      if (e.status !== 401) toast(errorText, 'error');
    } finally {
      btn.disabled = false;
    }
  }

  function exportExcel() {
    const month = $('#monthSel').value;
    download('/api/v1/sales/export' + (month ? '?month=' + encodeURIComponent(month) : ''), $('#btnExport'), 'ventes.xlsx', 'تعذر إنشاء ملف Excel.');
  }

  function backup() {
    download('/api/v1/admin/backup', $('#btnBackup'), 'fihi-chifae-backup.zip', 'تعذر إنشاء النسخة الاحتياطية.');
  }

  /* ---------------- init (listeners bound exactly once) ---------------- */
  function start() {
    const b = currentMonthBounds();
    $('#ordersFrom').value = b.from;
    $('#ordersTo').value = b.to;
    $('#ordersFrom').addEventListener('change', loadOrders);
    $('#ordersTo').addEventListener('change', loadOrders);
    $('#ordersResetBtn').addEventListener('click', () => {
      const c = currentMonthBounds();
      $('#ordersFrom').value = c.from;
      $('#ordersTo').value = c.to;
      loadOrders();
    });
    $$('.tab').forEach((tab) => tab.addEventListener('click', () => {
      statusFilter = tab.dataset.filter;
      $$('.tab').forEach((t) => { t.classList.toggle('active', t === tab); t.setAttribute('aria-selected', String(t === tab)); });
      renderOrders();
    }));
    $('#ordersList').addEventListener('click', onOrderAction);
    initCustomerFilter();
    $('#btnExport').addEventListener('click', exportExcel);
    $('#btnBackup').addEventListener('click', backup);
    initManualOrder();

    loadSummary().then(loadOrders);
    loadCatalogForOrders();
  }

  document.addEventListener('DOMContentLoaded', () => AdminAuth.require(start));
})();
