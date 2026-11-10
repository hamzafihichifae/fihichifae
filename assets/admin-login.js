/* fihi-chifae admin login: sets the HttpOnly session cookie, then returns to the requested page. */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };

  function nextUrl() {
    var next = new URLSearchParams(window.location.search).get('next') || '';
    // only same-site admin paths (no open redirect)
    return /^\/admin(-add)?\.html$/.test(next) ? next : '/admin.html';
  }

  function errMsg(data, fallback) {
    var e = data && data.error;
    return (e && e.message) || fallback;
  }

  function post(url, body) {
    return fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) { return { ok: r.ok, status: r.status, data: d }; });
    });
  }

  function toggleReset(show) {
    $('loginForm').hidden = show;
    $('resetForm').hidden = !show;
    $('loginMsg').textContent = '';
    $('resetMsg').textContent = '';
    (show ? $('resetEmail') : $('authUser')).focus();
  }

  $('forgotLink').addEventListener('click', function () { toggleReset(true); });
  $('backLoginLink').addEventListener('click', function () { toggleReset(false); });

  $('loginForm').addEventListener('submit', function (e) {
    e.preventDefault();
    var msg = $('loginMsg');
    var user = $('authUser').value.trim();
    var pass = $('authPass').value;
    msg.className = 'auth-error';
    if (!user || !pass) { msg.textContent = 'يرجى إدخال اسم المستخدم وكلمة المرور.'; return; }
    var btn = this.querySelector('button[type=submit]');
    btn.disabled = true;
    post('/api/v1/admin/session', { username: user, password: pass })
      .then(function (res) {
        if (res.ok && res.data.ok) { window.location.replace(nextUrl()); return; }
        var text = errMsg(res.data, 'بيانات الدخول غير صحيحة.');
        if (typeof res.data.remaining_attempts === 'number') text += ' (المحاولات المتبقية: ' + res.data.remaining_attempts + ')';
        msg.textContent = text;
        $('authPass').value = '';
      })
      .catch(function () { msg.textContent = 'تعذر الاتصال بالخادم.'; })
      .then(function () { btn.disabled = false; });
  });

  $('resetForm').addEventListener('submit', function (e) {
    e.preventDefault();
    var msg = $('resetMsg');
    var email = $('resetEmail').value.trim();
    msg.className = 'auth-error';
    if (!email) { msg.textContent = 'يرجى إدخال البريد الإلكتروني.'; return; }
    var btn = this.querySelector('button[type=submit]');
    btn.disabled = true;
    post('/api/v1/admin/reset/request', { email: email })
      .then(function (res) {
        if (res.ok) {
          toggleReset(false);
          $('loginMsg').className = 'auth-error ok';
          $('loginMsg').textContent = 'إذا كان البريد مسجلاً، سيصلك رابط الاستعادة.';
        } else {
          msg.textContent = errMsg(res.data, 'تعذر إرسال الطلب.');
        }
      })
      .catch(function () { msg.textContent = 'تعذر الاتصال بالخادم.'; })
      .then(function () { btn.disabled = false; });
  });

  $('authUser').focus();
})();
