/* fihi-chifae admin : shared helpers for the protected pages
   - the session lives in an HttpOnly cookie set by the server (never readable here)
   - api() serializes JSON bodies and sends the user back to the login page on 401
   - toast() gives non-blocking feedback (replaces alert()) */
(function () {
  'use strict';

  var LOGIN = '/admin-login.html';

  function goLogin() {
    var next = window.location.pathname + window.location.search;
    window.location.replace(LOGIN + '?next=' + encodeURIComponent(next));
  }

  function errMsg(data, fallback) {
    var e = data && data.error;
    if (typeof e === 'string') return e;
    if (e && typeof e.message === 'string') return e.message;
    return fallback;
  }

  /* fetch wrapper: plain objects are sent as JSON; resolves to the Response. */
  function api(path, opts) {
    opts = Object.assign({ credentials: 'same-origin', cache: 'no-store' }, opts || {});
    opts.headers = Object.assign({}, opts.headers || {});
    if (opts.body !== undefined && typeof opts.body !== 'string') {
      opts.body = JSON.stringify(opts.body);
      opts.headers['Content-Type'] = 'application/json';
    }
    return fetch(path, opts).then(function (res) {
      if (res.status === 401) {
        goLogin();
        var err = new Error('المصادقة مطلوبة');
        err.status = 401;
        throw err;
      }
      return res;
    });
  }

  /* api() + JSON decoding; throws Error(message) with .status/.payload on failure. */
  function apiJson(path, opts) {
    return api(path, opts).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) {
          var err = new Error(errMsg(data, 'خطأ في الخادم'));
          err.status = res.status;
          err.payload = data;
          throw err;
        }
        return data;
      });
    });
  }

  function require(cb) {
    fetch('/api/v1/admin/session', { credentials: 'same-origin', cache: 'no-store' })
      .then(function (r) { if (!r.ok) throw new Error('auth'); return r.json(); })
      .then(function (session) {
        var loading = document.getElementById('authLoading');
        var main = document.getElementById('mainContent');
        if (loading) loading.hidden = true;
        if (main) main.hidden = false;
        var lo = document.getElementById('btnLogout');
        if (lo) lo.addEventListener('click', logout);
        mountAvatar(session);
        cb();
      })
      .catch(goLogin);
  }

  /* ---------------- admin profile (avatar in the top bar + dialog) ---------------- */
  var profileState = { username: '', avatar: '' };

  function avatarInner(p, size) {
    if (p.avatar) return '<img src="' + esc(p.avatar) + '" alt="" width="' + size + '" height="' + size + '">';
    return '<span aria-hidden="true">' + esc((p.username || 'A').charAt(0).toUpperCase()) + '</span>';
  }

  function paintAvatars() {
    var btn = document.getElementById('profileBtn');
    if (btn) {
      btn.innerHTML = avatarInner(profileState, 40);
      btn.title = 'الملف الشخصي: ' + profileState.username;
    }
    var big = document.getElementById('pfAvatar');
    if (big) big.innerHTML = avatarInner(profileState, 76);
    var rm = document.getElementById('pfAvatarRemove');
    if (rm) rm.hidden = !profileState.avatar;
  }

  function mountAvatar(session) {
    var top = document.querySelector('header.top');
    if (!top || document.getElementById('profileBtn')) return;
    profileState.username = session.user || '';
    profileState.avatar = session.avatar || '';
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.id = 'profileBtn';
    btn.className = 'avatar-btn';
    btn.setAttribute('aria-label', 'الملف الشخصي');
    btn.addEventListener('click', openProfile);
    top.insertBefore(btn, top.firstChild); // first in RTL = right edge of the bar
    paintAvatars();
  }

  function field(id, label, type, extra) {
    return '<div class="field"><label for="' + id + '">' + label + '</label>' +
      '<input id="' + id + '" class="input" type="' + type + '" ' + (extra || '') + '></div>';
  }

  function openProfile() {
    var ov = document.createElement('div');
    ov.className = 'modal-overlay';
    ov.innerHTML =
      '<div class="modal-card profile-card" role="dialog" aria-modal="true" aria-labelledby="pfTitle">' +
      '  <div class="modal-head"><h3 id="pfTitle">الملف الشخصي</h3>' +
      '    <button class="modal-close" type="button" data-close aria-label="إغلاق">&times;</button></div>' +
      '  <form id="pfForm" novalidate>' +
      '  <div class="modal-body">' +
      '    <div class="pf-photo">' +
      '      <div class="pf-avatar" id="pfAvatar"></div>' +
      '      <div class="pf-photo-actions">' +
      '        <label class="btn-soft sm" for="pfFile">تغيير الصورة</label>' +
      '        <input type="file" id="pfFile" accept="image/png,image/jpeg,image/webp" hidden>' +
      '        <button type="button" class="btn-danger" id="pfAvatarRemove">إزالة الصورة</button>' +
      '        <span class="hint">اختيارية · PNG أو JPG أو WEBP، الحد 2 ميغا.</span>' +
      '      </div>' +
      '    </div>' +
      '    <div class="pf-grid">' +
      field('pfUser', 'اسم المستخدم (لتسجيل الدخول)', 'text', 'autocomplete="username" maxlength="40" dir="ltr" spellcheck="false"') +
      field('pfEmail', 'البريد الإلكتروني (لاستعادة كلمة المرور)', 'email', 'autocomplete="email" maxlength="254"') +
      field('pfPhone', 'رقم الهاتف / واتساب (يراسلك عليه الزبائن)', 'tel', 'autocomplete="tel" maxlength="20" placeholder="+212 6XX XXX XXX"') +
      '      <div class="pf-sep">تغيير كلمة المرور (اختياري)</div>' +
      field('pfNewPw', 'كلمة المرور الجديدة', 'password', 'autocomplete="new-password" minlength="8" maxlength="256"') +
      field('pfNewPw2', 'تأكيد كلمة المرور الجديدة', 'password', 'autocomplete="new-password" maxlength="256"') +
      '    </div>' +
      '  </div>' +
      '  <div class="modal-foot">' +
      '    <div class="field pf-current">' +
      '      <label for="pfCurrent">كلمة المرور الحالية <span class="req">*</span></label>' +
      '      <input id="pfCurrent" class="input" type="password" autocomplete="current-password" required>' +
      '    </div>' +
      '    <div class="modal-actions">' +
      '      <button type="button" class="btn-soft" data-close>إلغاء</button>' +
      '      <button type="submit" class="btn-primary" id="pfSave">حفظ التغييرات</button>' +
      '    </div>' +
      '  </div>' +
      '  </form>' +
      '</div>';
    document.body.appendChild(ov);
    document.body.style.overflow = 'hidden';
    var $ = function (id) { return document.getElementById(id); };
    var original = {};

    function close() {
      document.removeEventListener('keydown', onKey);
      ov.remove();
      document.body.style.overflow = '';
    }
    function onKey(e) { if (e.key === 'Escape') close(); }
    document.addEventListener('keydown', onKey);
    ov.addEventListener('click', function (e) { if (e.target === ov || e.target.closest('[data-close]')) close(); });
    paintAvatars();

    apiJson('/api/v1/admin/profile').then(function (data) {
      original = data.profile || {};
      $('pfUser').value = original.username || '';
      $('pfEmail').value = original.email || '';
      $('pfPhone').value = original.phone ? '+' + original.phone : '';
      profileState.username = original.username || '';
      profileState.avatar = original.avatar || '';
      paintAvatars();
      $('pfUser').focus();
    }).catch(function (err) { if (err.status !== 401) toast(err.message, 'error'); });

    $('pfFile').addEventListener('change', function () {
      var file = this.files[0];
      this.value = '';
      if (!file) return;
      if (file.size > 2 * 1024 * 1024) { toast('الصورة كبيرة جداً (الحد 2 ميغا).', 'error'); return; }
      var reader = new FileReader();
      reader.onload = function () {
        apiJson('/api/v1/admin/profile/avatar', { method: 'POST', body: { img: reader.result } })
          .then(function (data) { profileState.avatar = data.profile.avatar; paintAvatars(); toast('تم تحديث الصورة.'); })
          .catch(function (err) { if (err.status !== 401) toast(err.message, 'error'); });
      };
      reader.readAsDataURL(file);
    });
    $('pfAvatarRemove').addEventListener('click', function () {
      apiJson('/api/v1/admin/profile/avatar', { method: 'DELETE' })
        .then(function () { profileState.avatar = ''; paintAvatars(); toast('تمت إزالة الصورة.'); })
        .catch(function (err) { if (err.status !== 401) toast(err.message, 'error'); });
    });

    $('pfForm').addEventListener('submit', function (e) {
      e.preventDefault();
      var body = { current_password: $('pfCurrent').value };
      var user = $('pfUser').value.trim(), email = $('pfEmail').value.trim(), phone = $('pfPhone').value.trim();
      var pw = $('pfNewPw').value, pw2 = $('pfNewPw2').value;
      if (user !== (original.username || '')) body.username = user;
      if (email.toLowerCase() !== (original.email || '').toLowerCase()) body.email = email;
      if (phone.replace(/\D/g, '') !== (original.phone || '')) body.phone = phone;
      if (pw || pw2) {
        if (pw.length < 8) { toast('كلمة المرور الجديدة: 8 أحرف على الأقل.', 'error'); $('pfNewPw').focus(); return; }
        if (pw !== pw2) { toast('تأكيد كلمة المرور غير مطابق.', 'error'); $('pfNewPw2').focus(); return; }
        body.new_password = pw;
      }
      if (Object.keys(body).length === 1) { toast('لا توجد تغييرات للحفظ.'); return; }
      if (!body.current_password) { toast('أدخل كلمة المرور الحالية لتأكيد التغيير.', 'error'); $('pfCurrent').focus(); return; }
      var btn = $('pfSave');
      btn.disabled = true;
      apiJson('/api/v1/admin/profile', { method: 'PUT', body: body })
        .then(function (data) {
          profileState.username = data.profile.username;
          paintAvatars();
          close();
          toast(data.other_sessions_closed
            ? 'تم الحفظ. تم تسجيل الخروج من الأجهزة الأخرى.'
            : 'تم حفظ الملف الشخصي.');
        })
        .catch(function (err) {
          if (err.status !== 401) toast(err.message, 'error');
          btn.disabled = false;
        });
    });
  }

  function logout() {
    fetch('/api/v1/admin/session', { method: 'DELETE', credentials: 'same-origin' })
      .catch(function () { /* the cookie expires anyway */ })
      .then(function () { window.location.replace(LOGIN); });
  }

  function toast(msg, kind) {
    var box = document.getElementById('adminToasts');
    if (!box) {
      box = document.createElement('div');
      box.id = 'adminToasts';
      box.className = 'admin-toasts';
      box.setAttribute('role', 'status');
      box.setAttribute('aria-live', 'polite');
      document.body.appendChild(box);
    }
    var el = document.createElement('div');
    el.className = 'admin-toast ' + (kind === 'error' ? 'is-error' : 'is-ok');
    el.textContent = msg;
    box.appendChild(el);
    setTimeout(function () { el.classList.add('out'); setTimeout(function () { el.remove(); }, 300); }, kind === 'error' ? 5000 : 3000);
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (m) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m];
    });
  }

  /* One money format for the whole admin: 1,234.50 د.م. */
  function mad(n) {
    return Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' د.م.';
  }

  /* Accessible confirmation dialog; resolves to true/false. */
  function confirmDialog(message, okLabel, danger) {
    return new Promise(function (resolve) {
      var ov = document.createElement('div');
      ov.className = 'modal-overlay';
      ov.innerHTML =
        '<div class="modal-card narrow" role="alertdialog" aria-modal="true" aria-labelledby="cfTitle">' +
        '  <div class="modal-head"><h3 id="cfTitle">تأكيد</h3></div>' +
        '  <div class="modal-body"><p class="confirm-text"></p></div>' +
        '  <div class="modal-foot"><div class="modal-actions">' +
        '    <button type="button" class="btn-soft" data-no>إلغاء</button>' +
        '    <button type="button" class="' + (danger ? 'btn-danger' : 'btn-primary') + '" data-yes></button>' +
        '  </div></div>' +
        '</div>';
      ov.querySelector('.confirm-text').textContent = message;
      ov.querySelector('[data-yes]').textContent = okLabel || 'تأكيد';
      if (danger) ov.querySelector('[data-yes]').style.height = '2.6rem';
      function done(v) { document.removeEventListener('keydown', onKey); ov.remove(); resolve(v); }
      function onKey(e) { if (e.key === 'Escape') done(false); }
      ov.addEventListener('click', function (e) { if (e.target === ov) done(false); });
      ov.querySelector('[data-no]').addEventListener('click', function () { done(false); });
      ov.querySelector('[data-yes]').addEventListener('click', function () { done(true); });
      document.addEventListener('keydown', onKey);
      document.body.appendChild(ov);
      ov.querySelector('[data-yes]').focus();
    });
  }

  window.AdminAuth = {
    api: api, apiJson: apiJson, require: require, logout: logout,
    toast: toast, esc: esc, mad: mad, confirm: confirmDialog,
  };
})();
