/* fihi-chifae (فيه شفاء) - storefront : i18n (ar/fr/en), DB-driven catalog, cart,
   delivery fee, checkout (recorded server-side, then sent on WhatsApp), assistant. */

(function () {
  'use strict';

  /* ---------- helpers ---------- */
  const $ = (s, c) => (c || document).querySelector(s);
  const $$ = (s, c) => Array.from((c || document).querySelectorAll(s));
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));

  const BRAND = { ar: 'فيه <b>شفاء</b>', fr: 'fihi-<b>chifae</b>', en: 'fihi-<b>chifae</b>' };
  let WHATSAPP_NUMBER = '212681771457';

  const CART_ICON = '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="9" cy="21" r="1.6" fill="currentColor" stroke="none"/><circle cx="20" cy="21" r="1.6" fill="currentColor" stroke="none"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const TRASH_ICON = '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6" stroke-linecap="round"/></svg>';

  /* ---------- i18n ---------- */
  let LANG = 'ar';
  const NATIVE = { ar: 'العربية', fr: 'Français', en: 'English' };

  const T = {
    ar: {
      announce: 'التوصيل مجاني ابتداءً من 500 درهم وداخل البهاليل دائماً، وإلا فتكلفة التوصيل 40 درهم.',
      masthead_sub: 'الطبيعة المغربية',
      account: 'حسابي', menu: 'القائمة', close: 'إغلاق', categories: 'الفئات', send: 'إرسال', info_link: 'معلومات ومساعدة',
      cart_title: 'السلة ({n})',
      search_placeholder: 'ابحث عن منتج', search_btn: 'بحث', open_cart: 'فتح السلة', view_cart: 'مشاهدة السلة',
      hero_title: '"فيه شفاء"... الطعم الأصيل للطبيعة المغربية، منتجات طبيعية 100% بدون إضافات',
      hero_sub: 'العسل المغربي الخالص... كما يجب أن يكون', hero_cta: 'اكتشف منتجاتنا',
      trust_natural: '100% طبيعي', trust_delivery: 'التوصيل داخل المغرب', trust_additives: 'بدون إضافات',
      hf1_sub: 'ضمان بدون إضافات', hf2_title: 'الدفع عند الاستلام', hf2_sub: 'في جميع أنحاء المغرب',
      featured_eyebrow: 'أفضل مبيعاتنا', featured_title: 'المنتجات الأكثر مبيعاً',
      featured_sub: 'تشكيلة من المنتجات المفضلة لدى عملائنا، مباشرة من قلب الطبيعة المغربية.',
      strip1_title: 'منتجات طازجة', strip1_sub: 'محضّرة بعناية', strip2_title: 'توصيل سريع', strip2_sub: 'في جميع أنحاء المغرب',
      strip3_title: 'الدفع عند الاستلام', strip3_sub: 'قرب منزلك', strip4_title: '100% طبيعي', strip4_sub: 'بدون إضافات',
      news_title: 'توصل بآخر المنتجات والعروض الحصرية', news_sub: 'مباشرة إلى بريدك الإلكتروني',
      news_placeholder: 'أدخل بريدك الإلكتروني', news_btn: 'اشترك',
      footer_brand: 'فيه شفاء علامة مغربية من البهاليل متخصصة في العسل الطبيعي ومنتجات الخلية والزيوت التقليدية، نختارها بعناية من قلب الطبيعة المغربية.',
      fc1_title: 'الشركة', fc1_about: 'من نحن', fc1_products: 'منتجاتنا وفوائدها', fc1_privacy: 'سياسة الخصوصية', fc1_terms: 'شروط الاستخدام', fc1_faq: 'الأسئلة الشائعة',
      fc2_title: 'مساعدة', fc2_track: 'تتبع الطلبية عبر واتساب', fc2_ship: 'الشحن والتوصيل', fc2_return: 'سياسة الإرجاع',
      fc3_title: 'تواصل معنا', fc3_wa: 'واتساب: اطلب أو استفسر', fc3_city: 'البهاليل، إقليم صفرو، المغرب',
      copyright: 'جميع الحقوق محفوظة © 2026 فيه شفاء',
      wa_chat: 'مساعدة عبر المحادثة', wa_bot_name: 'فيه شفاء - المساعد', wa_bot_status: 'متصل الآن • يرد عادة خلال دقائق', wa_bot_placeholder: 'اكتب رسالتك...',
      search_hint: 'اكتب اسم منتج لبدء البحث.', search_ph: 'ابحث عن منتج...', no_results: 'لا يوجد منتج يطابق « {q} »',
      price_from: 'من {p}', count_products: '{n} منتوج', add_to_cart: 'أضف إلى السلة', details: 'التفاصيل', promo: 'عرض', price_on_request: 'السعر عند الطلب',
      cart_empty: 'سلتك فارغة.', cart_remove: 'إزالة', cart_dec: 'تخفيض', cart_inc: 'زيادة',
      subtotal_label: 'المنتجات', delivery_label: 'التوصيل', cart_total_label: 'المجموع', free: 'مجاني',
      delivery_hint_free_city: 'التوصيل مجاني داخل البهاليل.', delivery_hint_free_amount: 'التوصيل مجاني لأن طلبك تجاوز 500 درهم.',
      delivery_hint_add: 'أضف {n} للحصول على توصيل مجاني.', delivery_hint_city: 'أدخل مدينتك لحساب التوصيل.',
      checkout_title: 'معلومات التوصيل', checkout_btn: 'تأكيد الطلب عبر واتساب',
      checkout_name: 'الاسم الكامل *', checkout_phone: 'رقم الهاتف *', checkout_city: 'المدينة *',
      checkout_address: 'العنوان (الشارع، الحي، رقم المنزل) *', checkout_location: 'رابط الموقع على الخريطة (اختياري)',
      use_location: 'استعمل موقعي الحالي', locating: 'جاري تحديد موقعك…', location_ok: 'تمت إضافة رابط موقعك.', location_fail: 'تعذر تحديد الموقع، يمكنك لصق الرابط يدوياً.',
      name_required: 'يرجى إدخال اسمك الكامل.', phone_required: 'يرجى إدخال رقم هاتف صحيح.', address_required: 'يرجى إدخال العنوان.',
      city_required: 'يرجى إدخال المدينة.', location_invalid: 'رابط الموقع يجب أن يبدأ بـ https://',
      newsletter_invalid: 'يرجى إدخال بريد إلكتروني صحيح.', newsletter_ok: 'شكراً! تم اشتراكك بنجاح.', newsletter_fail: 'تعذر الاشتراك، حاول لاحقاً.',
      added_to_cart: 'تمت إضافة « {p} » إلى السلة', order_sending: 'جاري تسجيل طلبك…',
      order_success: 'تم تسجيل طلبك! أكمل الإرسال على واتساب ليتواصل معك البائع.', order_error: 'تعذر إرسال الطلب. يرجى المحاولة مرة أخرى.',
      cart_refreshed: 'تم تحديث المنتجات، يرجى مراجعة السلة.', choose_size: 'اختر الحجم أولاً',
      catalog_offline: 'تعذر تحميل المنتجات. يرجى إعادة تحميل الصفحة.', catalog_empty: 'سيتم إضافة المنتجات قريباً.',
      wa_template: 'مرحباً، طلبية جديدة من متجر فيه شفاء 🛒\nرقم الطلب: {ID}\n\nالمنتجات:\n{LINES}\nالمنتجات: {SUB}\nالتوصيل: {FEE}\nالمجموع: {TOTAL}\n\nالاسم: {NAME}\nالهاتف: {PHONE}\nالمدينة: {CITY}\nالعنوان: {ADDRESS}\nالموقع: {LOCATION}\n\nشكراً لكم 🌿',
    },
    fr: {
      announce: 'Livraison gratuite dès 500 MAD et toujours à BHALIL, sinon 40 MAD.',
      masthead_sub: 'Maroc naturel',
      account: 'Mon compte', menu: 'Menu', close: 'Fermer', categories: 'Catégories', send: 'Envoyer', info_link: 'Infos & aide',
      cart_title: 'Panier ({n})',
      search_placeholder: 'Rechercher un produit', search_btn: 'Rechercher', open_cart: 'Ouvrir le panier', view_cart: 'Voir le panier',
      hero_title: 'fihi-chifae... le goût authentique de la nature marocaine, des produits 100% naturels sans additifs.',
      hero_sub: 'Le miel pur marocain... comme il doit être', hero_cta: 'Découvrez nos produits',
      trust_natural: '100% Naturel', trust_delivery: 'Livraison au Maroc', trust_additives: 'Sans additifs',
      hf1_sub: 'garanti sans additifs', hf2_title: 'Paiement à la livraison', hf2_sub: 'partout au Maroc',
      featured_eyebrow: 'Nos coups de cœur', featured_title: 'Produits les plus vendus',
      featured_sub: 'Une sélection des produits préférés de nos clients, directement du cœur de la nature marocaine.',
      strip1_title: 'Produits frais', strip1_sub: 'récoltés avec soin', strip2_title: 'Livraison rapide', strip2_sub: 'partout au Maroc',
      strip3_title: 'Paiement à la livraison', strip3_sub: 'près de chez vous', strip4_title: '100% Naturel', strip4_sub: 'sans additifs',
      news_title: 'Recevez les derniers produits et offres exclusives', news_sub: 'directement dans votre boîte mail',
      news_placeholder: 'Entrez votre e-mail', news_btn: "S'abonner",
      footer_brand: 'fihi-chifae est une marque marocaine de BHALIL spécialisée dans le miel naturel, les produits de la ruche et les huiles traditionnelles, sélectionnés avec soin au cœur de la nature marocaine.',
      fc1_title: 'Entreprise', fc1_about: 'À propos', fc1_products: 'Nos produits et leurs bienfaits', fc1_privacy: 'Politique de confidentialité', fc1_terms: "Conditions d'utilisation", fc1_faq: 'Questions fréquentes',
      fc2_title: 'Aide', fc2_track: 'Suivre ma commande sur WhatsApp', fc2_ship: 'Expédition et livraison', fc2_return: 'Politique de retour',
      fc3_title: 'Nous contacter', fc3_wa: 'WhatsApp : commander ou poser une question', fc3_city: 'BHALIL, province de Sefrou, Maroc',
      copyright: '© 2026 fihi-chifae. Tous droits réservés.',
      wa_chat: "Besoin d'aide ? Discutons", wa_bot_name: 'fihi-chifae - Assistant', wa_bot_status: 'En ligne • répond en quelques minutes', wa_bot_placeholder: 'Écrivez votre message...',
      search_hint: 'Tapez un nom de produit pour lancer la recherche.', search_ph: 'Rechercher un produit...', no_results: 'Aucun produit ne correspond à « {q} »',
      price_from: 'Dès {p}', count_products: '{n} produits', add_to_cart: 'Ajouter au panier', details: 'Détails', promo: 'Promo', price_on_request: 'Prix sur demande',
      cart_empty: 'Votre panier est vide.', cart_remove: 'Retirer', cart_dec: 'Diminuer', cart_inc: 'Augmenter',
      subtotal_label: 'Produits', delivery_label: 'Livraison', cart_total_label: 'Total', free: 'Gratuite',
      delivery_hint_free_city: 'Livraison gratuite à BHALIL.', delivery_hint_free_amount: 'Livraison offerte : votre commande dépasse 500 MAD.',
      delivery_hint_add: 'Ajoutez {n} pour la livraison gratuite.', delivery_hint_city: 'Indiquez votre ville pour calculer la livraison.',
      checkout_title: 'Informations de livraison', checkout_btn: 'Valider la commande sur WhatsApp',
      checkout_name: 'Nom complet *', checkout_phone: 'Téléphone *', checkout_city: 'Ville *',
      checkout_address: 'Adresse (rue, quartier, n°) *', checkout_location: 'Lien de localisation (optionnel)',
      use_location: 'Utiliser ma position', locating: 'Localisation en cours…', location_ok: 'Lien de votre position ajouté.', location_fail: 'Position indisponible, collez le lien manuellement.',
      name_required: 'Veuillez saisir votre nom complet.', phone_required: 'Veuillez saisir un numéro de téléphone valide.', address_required: "Veuillez saisir l'adresse.",
      city_required: 'Veuillez saisir la ville.', location_invalid: 'Le lien de localisation doit commencer par https://',
      newsletter_invalid: 'Veuillez saisir un e-mail valide.', newsletter_ok: 'Merci ! Vous êtes bien abonné(e).', newsletter_fail: "Inscription impossible, réessayez plus tard.",
      added_to_cart: '« {p} » ajouté au panier', order_sending: 'Enregistrement de votre commande…',
      order_success: 'Commande enregistrée ! Terminez l’envoi sur WhatsApp pour que le vendeur vous contacte.', order_error: "Impossible d'envoyer la commande. Réessayez.",
      cart_refreshed: 'Les produits ont changé, vérifiez votre panier.', choose_size: "Choisissez d'abord un format",
      catalog_offline: 'Impossible de charger les produits. Rechargez la page.', catalog_empty: 'Les produits arrivent bientôt.',
      wa_template: 'Bonjour, nouvelle commande fihi-chifae 🛒\nN° de commande : {ID}\n\nProduits :\n{LINES}\nProduits : {SUB}\nLivraison : {FEE}\nTotal : {TOTAL}\n\nNom : {NAME}\nTéléphone : {PHONE}\nVille : {CITY}\nAdresse : {ADDRESS}\nLocalisation : {LOCATION}\n\nMerci 🌿',
    },
    en: {
      announce: 'Free delivery from 500 MAD and always in BHALIL, otherwise 40 MAD.',
      masthead_sub: 'Natural Morocco',
      account: 'My account', menu: 'Menu', close: 'Close', categories: 'Categories', send: 'Send', info_link: 'Info & help',
      cart_title: 'Cart ({n})',
      search_placeholder: 'Search for a product', search_btn: 'Search', open_cart: 'Open cart', view_cart: 'View cart',
      hero_title: 'fihi-chifae... the authentic taste of Moroccan nature, 100% natural products with no additives.',
      hero_sub: 'Pure Moroccan honey... as it should be', hero_cta: 'Discover our products',
      trust_natural: '100% Natural', trust_delivery: 'Delivery in Morocco', trust_additives: 'No additives',
      hf1_sub: 'guaranteed no additives', hf2_title: 'Cash on delivery', hf2_sub: 'anywhere in Morocco',
      featured_eyebrow: 'Our favourites', featured_title: 'Best selling products',
      featured_sub: 'A selection of our customers’ favourite products, straight from the heart of Moroccan nature.',
      strip1_title: 'Fresh products', strip1_sub: 'harvested with care', strip2_title: 'Fast delivery', strip2_sub: 'anywhere in Morocco',
      strip3_title: 'Cash on delivery', strip3_sub: 'close to you', strip4_title: '100% Natural', strip4_sub: 'no additives',
      news_title: 'Get the latest products and exclusive offers', news_sub: 'straight to your inbox',
      news_placeholder: 'Enter your email', news_btn: 'Subscribe',
      footer_brand: 'fihi-chifae is a Moroccan brand from BHALIL specialised in natural honey, hive products and traditional oils, carefully selected from the heart of Moroccan nature.',
      fc1_title: 'Company', fc1_about: 'About us', fc1_products: 'Our products & benefits', fc1_privacy: 'Privacy policy', fc1_terms: 'Terms of use', fc1_faq: 'FAQ',
      fc2_title: 'Help', fc2_track: 'Track my order on WhatsApp', fc2_ship: 'Shipping and delivery', fc2_return: 'Return policy',
      fc3_title: 'Contact us', fc3_wa: 'WhatsApp: order or ask a question', fc3_city: 'BHALIL, Sefrou province, Morocco',
      copyright: '© 2026 fihi-chifae. All rights reserved.',
      wa_chat: 'Need help? Chat with us', wa_bot_name: 'fihi-chifae - Assistant', wa_bot_status: 'Online • replies in minutes', wa_bot_placeholder: 'Type a message...',
      search_hint: 'Type a product name to start searching.', search_ph: 'Search for a product...', no_results: 'No product matches « {q} »',
      price_from: 'From {p}', count_products: '{n} products', add_to_cart: 'Add to cart', details: 'Details', promo: 'Promo', price_on_request: 'Price on request',
      cart_empty: 'Your cart is empty.', cart_remove: 'Remove', cart_dec: 'Decrease', cart_inc: 'Increase',
      subtotal_label: 'Products', delivery_label: 'Delivery', cart_total_label: 'Total', free: 'Free',
      delivery_hint_free_city: 'Free delivery in BHALIL.', delivery_hint_free_amount: 'Free delivery: your order is over 500 MAD.',
      delivery_hint_add: 'Add {n} more for free delivery.', delivery_hint_city: 'Enter your city to compute delivery.',
      checkout_title: 'Delivery details', checkout_btn: 'Place order via WhatsApp',
      checkout_name: 'Full name *', checkout_phone: 'Phone *', checkout_city: 'City *',
      checkout_address: 'Address (street, area, number) *', checkout_location: 'Map location link (optional)',
      use_location: 'Use my current location', locating: 'Locating you…', location_ok: 'Your location link was added.', location_fail: 'Location unavailable, paste the link manually.',
      name_required: 'Please enter your full name.', phone_required: 'Please enter a valid phone number.', address_required: 'Please enter your address.',
      city_required: 'Please enter your city.', location_invalid: 'The location link must start with https://',
      newsletter_invalid: 'Please enter a valid email.', newsletter_ok: 'Thank you! You are now subscribed.', newsletter_fail: 'Subscription failed, please try later.',
      added_to_cart: '« {p} » added to cart', order_sending: 'Recording your order…',
      order_success: 'Order recorded! Finish sending it on WhatsApp so the seller can contact you.', order_error: 'Unable to send the order. Please try again.',
      cart_refreshed: 'Products changed, please review your cart.', choose_size: 'Choose a size first',
      catalog_offline: 'Unable to load products. Please reload the page.', catalog_empty: 'Products are coming soon.',
      wa_template: 'Hello, new fihi-chifae order 🛒\nOrder no.: {ID}\n\nProducts:\n{LINES}\nProducts: {SUB}\nDelivery: {FEE}\nTotal: {TOTAL}\n\nName: {NAME}\nPhone: {PHONE}\nCity: {CITY}\nAddress: {ADDRESS}\nLocation: {LOCATION}\n\nThank you 🌿',
    },
  };

  function t(key, sub) {
    let s = (T[LANG] && T[LANG][key]) || T.ar[key] || key;
    if (sub !== undefined && sub !== null) s = s.replace(/\{[pnq]\}/g, String(sub));
    return s;
  }

  /* One price format per language: "350.00 د.م." (ar), "350,00 MAD" (fr), "350.00 MAD" (en). */
  function money(n) {
    const s = Number(n || 0).toFixed(2);
    if (LANG === 'ar') return s + ' د.م.';
    return (LANG === 'fr' ? s.replace('.', ',') : s) + ' MAD';
  }

  /* ---------- data ---------- */
  const DATA = { categories: [], featured: [] };
  let loaded = false;
  let loading = true;

  function loadCatalog() {
    return fetch('/api/v1/catalog', { cache: 'no-cache' })
      .then((r) => { if (!r.ok) throw new Error('api'); return r.json(); })
      .then((data) => {
        DATA.categories = data.categories || [];
        DATA.featured = data.featured || [];
        if (data.settings) {
          if (data.settings.whatsapp) applyPhone(data.settings.whatsapp);
          if (window.Delivery) Delivery.configure(data.settings);
        }
        loaded = true;
      })
      .catch(() => { loaded = false; })
      .then(() => { loading = false; });
  }

  /* The shop number is set by the admin: refresh every WhatsApp / phone link. */
  function applyPhone(raw) {
    const digits = String(raw || '').replace(/\D/g, '');
    if (digits.length < 9) return;
    WHATSAPP_NUMBER = digits;
    $$('a[href^="https://wa.me/"]').forEach((a) => {
      const u = new URL(a.href);
      a.href = 'https://wa.me/' + digits + u.search;
    });
    $$('a[href^="tel:"]').forEach((a) => { a.href = 'tel:+' + digits; });
    $$('[data-shop-phone]').forEach((el) => { el.textContent = phoneText(digits); });
  }
  // 212681771457 -> +212 681 771 457 (always left to right)
  function phoneText(d) {
    return d.startsWith('212') && d.length === 12
      ? '+212 ' + d.slice(3, 6) + ' ' + d.slice(6, 9) + ' ' + d.slice(9)
      : '+' + d;
  }

  const allProducts = () => {
    const out = [];
    DATA.categories.forEach((c) => c.products.forEach((p) => out.push(Object.assign({}, p, { cat: c.id, img: p.img || c.img }))));
    return out;
  };
  const findProduct = (id) => allProducts().find((p) => p.id === id) || DATA.featured.find((p) => p.id === id);
  const catImg = (slug) => { const c = DATA.categories.find((x) => x.id === slug); return c ? c.img : '/media/cat-default.svg'; };

  /* ---------- i18n apply ---------- */
  function applyI18n() {
    document.documentElement.lang = LANG;
    document.documentElement.dir = LANG === 'ar' ? 'rtl' : 'ltr';
    $('#langCurrent').textContent = NATIVE[LANG];
    $$('#langMenu .lang-item').forEach((el) => el.classList.toggle('active', el.dataset.lang === LANG));
    $$('.footer-lang a').forEach((el) => el.classList.toggle('active', el.dataset.lang === LANG));
    $$('.logo-text').forEach((el) => { el.innerHTML = BRAND[LANG]; });

    $$('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n.replace(/-/g, '_')); });
    $$('[data-i18n-ph]').forEach((el) => { el.placeholder = t(el.dataset.i18nPh.replace(/-/g, '_')); });
    $$('[data-i18n-title]').forEach((el) => { el.title = t(el.dataset.i18nTitle.replace(/-/g, '_')); });
    $$('[data-i18n-aria]').forEach((el) => { el.setAttribute('aria-label', t(el.dataset.i18nAria.replace(/-/g, '_'))); });

    const ph = { searchInput: 'search_placeholder', checkoutName: 'checkout_name', checkoutPhone: 'checkout_phone',
      checkoutCity: 'checkout_city', checkoutAddress: 'checkout_address', checkoutLocation: 'checkout_location' };
    Object.keys(ph).forEach((id) => {
      const el = document.getElementById(id);
      if (el) { el.placeholder = t(ph[id]); el.setAttribute('aria-label', t(ph[id]).replace(' *', '')); }
    });
    $('#btnLocate').title = t('use_location');

    renderCatalog();
    renderCart();
  }

  function setLang(l) {
    if (!T[l]) return;
    LANG = l;
    try { localStorage.setItem('dhenbio_lang', l); } catch (e) { /* private mode */ }
    applyI18n();
  }

  /* ---------- product cards ---------- */
  const validSizes = (p) => (p && p.sizes ? p.sizes : []).filter((s) => s && s.size);
  const sizeLabel = (s) => String(s.size) + String(s.unit || ''); // id sent to the server ("250g")
  // shown to people as "<value> <unit>" (250 g) in every language, inside dir="ltr"
  const sizeText = (id) => String(id || '').replace(/^([\d.,]+)\s*(g|kg|L)$/i, '$1 $2');

  function priceLabel(p) {
    const sp = validSizes(p).map((s) => Number(s.price)).filter((v) => !isNaN(v));
    if (sp.length) {
      const lo = Math.min.apply(null, sp), hi = Math.max.apply(null, sp);
      return lo === hi ? money(lo) : t('price_from', money(lo));
    }
    if (p.min) return money(p.min);
    return t('price_on_request');
  }

  function sizeChips(p) {
    const sizes = validSizes(p);
    if (!sizes.length) return '';
    return '<div class="prod-sizes" role="group" aria-label="' + esc(t('choose_size')) + '">' +
      sizes.map((s) => '<button type="button" class="size-chip" dir="ltr" data-size="' + esc(sizeLabel(s)) + '" data-price="' + esc(s.price) + '">' + esc(sizeText(sizeLabel(s))) + '</button>').join('') +
      '</div>';
  }

  function cardHTML(p) {
    const img = p.img || catImg(p.cat);
    return (
      '<article class="prod-card" data-id="' + esc(p.id) + '">' +
      '  <button type="button" class="prod-media" data-details aria-label="' + esc(t('details') + ': ' + p.name) + '">' +
      (p.ribbon ? '<span class="prod-ribbon">' + esc(t('promo')) + '</span>' : '') +
      '    <img src="' + esc(img) + '" alt="" loading="lazy">' +
      '  </button>' +
      '  <div class="prod-body">' +
      '    <h3 class="prod-name"><button type="button" data-details>' + esc(p.name) + '</button></h3>' +
      '    <span class="prod-price">' + esc(priceLabel(p)) + '</span>' +
      sizeChips(p) +
      '    <button type="button" class="btn-add">' + CART_ICON + '<span>' + esc(t('add_to_cart')) + '</span></button>' +
      '  </div>' +
      '</article>'
    );
  }

  function emptyMsg(key) { return '<div class="grid-empty">' + esc(t(key)) + '</div>'; }

  /* ---------- render catalog ---------- */
  function renderCatalog() {
    const featured = $('#featuredGrid');
    const wrap = $('#catSections');
    if (!loaded) {
      featured.innerHTML = loading ? '' : emptyMsg('catalog_offline');
      wrap.innerHTML = '';
      renderCatBar();
      return;
    }
    const hasProducts = allProducts().length > 0;
    // no best sellers yet but a catalog exists: skip the section; nothing at all: say so
    $('#featured').hidden = !DATA.featured.length && hasProducts;
    featured.innerHTML = DATA.featured.length ? DATA.featured.map(cardHTML).join('') : emptyMsg('catalog_empty');
    featured.style.setProperty('--cols', String(Math.max(1, Math.min(5, DATA.featured.length))));

    wrap.innerHTML = DATA.categories.filter((c) => c.products.length).map((cat) => {
      const title = cat['title_' + LANG] || cat.title_ar;
      return (
        '<section class="cat-section" id="cat-' + esc(cat.id) + '">' +
        '  <button type="button" class="cat-head" aria-expanded="true">' +
        '    <h2>' + esc(title) + '</h2>' +
        '    <span class="count">' + esc(t('count_products', cat.products.length)) + '</span>' +
        '    <svg class="cat-caret" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m6 9 6 6 6-6" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
        '  </button>' +
        '  <div class="prod-grid cat-body">' + cat.products.map((p) => cardHTML(Object.assign({}, p, { cat: cat.id, img: p.img || cat.img }))).join('') + '</div>' +
        '</section>'
      );
    }).join('');
    renderCatBar();
    observeSections();
  }

  function renderCatBar() {
    const cats = loaded ? DATA.categories.filter((c) => c.products.length) : [];
    const title = (c) => esc(c['title_' + LANG] || c.title_ar);
    $('#catBar').innerHTML = cats.map((c) => '<a href="#cat-' + esc(c.id) + '" class="cat-link">' + title(c) + '</a>').join('');
    $('#mobileNav').innerHTML = cats.map((c) => '<a href="#cat-' + esc(c.id) + '" class="mobile-nav-link">' + title(c) + '</a>').join('');
  }

  let sectionObserver = null;
  function observeSections() {
    if (sectionObserver) sectionObserver.disconnect();
    if (!('IntersectionObserver' in window)) return;
    sectionObserver = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting) $$('.cat-link').forEach((l) => l.classList.toggle('active', l.getAttribute('href') === '#' + en.target.id));
      });
    }, { rootMargin: '-40% 0px -55% 0px' });
    $$('.cat-section').forEach((s) => sectionObserver.observe(s));
  }

  /* ---------- product details ---------- */
  function openDetails(id) {
    const p = findProduct(id);
    if (!p) return;
    const img = p.img || catImg(p.cat);
    $('#pdImg').src = img;
    $('#pdImg').alt = p.name;
    const cat = DATA.categories.find((c) => c.id === p.cat);
    $('#pdBody').innerHTML =
      '<article class="prod-card pd-inner" data-id="' + esc(p.id) + '">' +
      (cat ? '<span class="eyebrow">' + esc(cat['title_' + LANG] || cat.title_ar) + '</span>' : '') +
      '<h3 class="pd-name" id="pdName">' + esc(p.name) + '</h3>' +
      '<span class="prod-price">' + esc(priceLabel(p)) + '</span>' +
      (p.description ? '<p class="pd-desc">' + esc(p.description) + '</p>' : '') +
      sizeChips(p) +
      '<button type="button" class="btn-add">' + CART_ICON + '<span>' + esc(t('add_to_cart')) + '</span></button>' +
      '</article>';
    $('#productModal').hidden = false;
    document.body.style.overflow = 'hidden';
    $('#pdClose').focus();
  }

  function closeDetails() {
    $('#productModal').hidden = true;
    if (!$('#cartDrawer').classList.contains('open')) document.body.style.overflow = '';
  }

  /* ---------- cart ---------- */
  let cart = [];
  try { cart = JSON.parse(localStorage.getItem('dhenbio_cart') || '[]'); } catch (e) { cart = []; }
  if (!Array.isArray(cart)) cart = [];

  const saveCart = () => { try { localStorage.setItem('dhenbio_cart', JSON.stringify(cart)); } catch (e) { /* ignore */ } };
  const cartCount = () => cart.reduce((s, it) => s + it.qty, 0);
  const cartSubtotal = () => cart.reduce((s, it) => s + it.qty * (Number(it.price) || 0), 0);
  const currentFee = () => (window.Delivery ? Delivery.fee(cartSubtotal(), $('#checkoutCity').value) : 0);

  function addToCart(p, size, price) {
    const existing = cart.find((it) => (it.id ? it.id === p.id : it.name === p.name) && (it.size || '') === (size || ''));
    if (existing) existing.qty += 1;
    else cart.push({ id: p.id, name: p.name, price: Number(price) || 0, img: p.img || catImg(p.cat), cat: p.cat, qty: 1, size: size || '' });
    saveCart();
    renderCart();
    toast(t('added_to_cart', p.name));
  }

  function renderTotals() {
    const sub = cartSubtotal();
    const city = $('#checkoutCity').value.trim();
    const fee = currentFee();
    $('#cartSubtotal').textContent = money(sub);
    $('#cartDelivery').textContent = !city ? '—' : (fee ? money(fee) : t('free'));
    $('#cartTotal').textContent = money(sub + fee);
    let hint = '';
    const threshold = window.Delivery ? Delivery.settings.free_delivery_threshold : 500;
    if (!city) hint = t('delivery_hint_city');
    else if (window.Delivery && Delivery.isFreeCity(city)) hint = t('delivery_hint_free_city');
    else if (sub >= threshold) hint = t('delivery_hint_free_amount');
    else hint = t('delivery_hint_add', money(threshold - sub));
    $('#deliveryHint').textContent = hint;
  }

  function renderCart() {
    $('#cartCount').textContent = String(cartCount());
    $('#cartTitle').textContent = t('cart_title', cartCount());
    const items = $('#cartItems');
    const hasItems = cart.length > 0;
    $('#cartFoot').hidden = !hasItems;
    $('#checkoutForm').hidden = !hasItems;
    if (!hasItems) {
      items.innerHTML = '<div class="cart-empty">' + CART_ICON + '<p>' + esc(t('cart_empty')) + '</p></div>';
      return;
    }
    items.innerHTML = '<ul class="cart-items">' + cart.map((it, i) =>
      '<li class="cart-item">' +
      '  <img src="' + esc(it.img) + '" alt="">' +
      '  <div class="cart-item-info"><b>' + esc(it.name) + (it.size ? ' <span class="size-tag" dir="ltr">' + esc(sizeText(it.size)) + '</span>' : '') + '</b>' +
      '    <span>' + esc(money(it.price)) + '</span>' +
      '    <div class="qty"><button type="button" data-dec="' + i + '" aria-label="' + esc(t('cart_dec')) + '">−</button><em>' + it.qty + '</em><button type="button" data-inc="' + i + '" aria-label="' + esc(t('cart_inc')) + '">+</button></div>' +
      '  </div>' +
      '  <button type="button" class="cart-item-del" data-del="' + i + '" aria-label="' + esc(t('cart_remove')) + '">' + TRASH_ICON + '</button>' +
      '</li>').join('') + '</ul>';
    renderTotals();
  }

  function onCartClick(e) {
    const b = e.target.closest('[data-dec],[data-inc],[data-del]');
    if (!b) return;
    const i = Number(b.dataset.dec ?? b.dataset.inc ?? b.dataset.del);
    if (!cart[i]) return;
    if (b.dataset.del !== undefined) cart.splice(i, 1);
    else {
      cart[i].qty += b.dataset.inc !== undefined ? 1 : -1;
      if (cart[i].qty <= 0) cart.splice(i, 1);
    }
    saveCart();
    renderCart();
  }

  /* One delegated handler for every product card on the page (bound once). */
  function onCardClick(e) {
    const card = e.target.closest('.prod-card');
    if (!card) return;
    const chip = e.target.closest('.size-chip');
    if (chip) {
      $$('.size-chip', card).forEach((c) => c.classList.toggle('selected', c === chip));
      const priceEl = $('.prod-price', card);
      if (priceEl) priceEl.textContent = money(parseFloat(chip.dataset.price));
      return;
    }
    if (e.target.closest('[data-details]')) { openDetails(card.dataset.id); return; }
    if (e.target.closest('.btn-add')) {
      const p = findProduct(card.dataset.id);
      if (!p) return;
      const sizes = validSizes(p);
      if (sizes.length) {
        const sel = $('.size-chip.selected', card);
        if (!sel) { toast(t('choose_size')); $('.size-chip', card).focus(); return; }
        addToCart(p, sel.dataset.size, parseFloat(sel.dataset.price));
      } else {
        addToCart(p, '', p.min || 0);
      }
    }
  }

  /* ---------- checkout ---------- */
  function readCustomer() {
    return {
      buyer: $('#checkoutName').value.trim(),
      phone: $('#checkoutPhone').value.trim(),
      city: window.Delivery ? Delivery.normalizeCity($('#checkoutCity').value) : $('#checkoutCity').value.trim(),
      address: $('#checkoutAddress').value.trim(),
      location: $('#checkoutLocation').value.trim(),
    };
  }

  function validateCustomer(c) {
    if (!c.buyer) return ['name_required', '#checkoutName'];
    if (c.phone.replace(/\D/g, '').length < 8) return ['phone_required', '#checkoutPhone'];
    if (!c.city) return ['city_required', '#checkoutCity'];
    if (!c.address) return ['address_required', '#checkoutAddress'];
    if (c.location && !/^https?:\/\//i.test(c.location)) return ['location_invalid', '#checkoutLocation'];
    return null;
  }

  function waMessage(order, c) {
    const lines = order.items.map((it) => '• ' + it.qty + ' × ' + it.name + (it.size ? ' (' + sizeText(it.size) + ')' : '') + ' — ' + money(it.price * it.qty)).join('\n');
    return t('wa_template')
      .replace('{ID}', order.order_id)
      .replace('{LINES}', lines)
      .replace('{SUB}', money(order.subtotal))
      .replace('{FEE}', order.delivery_fee ? money(order.delivery_fee) : t('free'))
      .replace('{TOTAL}', money(order.total))
      .replace('{NAME}', c.buyer)
      .replace('{PHONE}', c.phone)
      .replace('{CITY}', order.city || c.city)
      .replace('{ADDRESS}', c.address)
      .replace('{LOCATION}', c.location || '—');
  }

  /* Records the order on the server first (prices + delivery are computed there),
     then hands the summary to WhatsApp. Returns true on success. */
  async function placeOrder(source) {
    if (!cart.length) { toast(t('cart_empty')); return false; }
    const c = readCustomer();
    const invalid = validateCustomer(c);
    if (invalid) {
      toast(t(invalid[0]));
      openCart();
      const el = $(invalid[1]);
      el.focus();
      el.setAttribute('aria-invalid', 'true');
      return false;
    }
    const btn = $('#checkoutBtn');
    btn.disabled = true;
    // open the WhatsApp tab inside the click gesture (popup blockers), fill it once the order is saved
    const win = window.open('', '_blank');
    toast(t('order_sending'));
    try {
      const res = await fetch('/api/v1/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.assign({}, c, {
          source: source || 'online',
          items: cart.map((it) => ({ id: it.id, name: it.name, cat: it.cat, size: it.size || '', qty: it.qty })),
        })),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const err = new Error((data.error && data.error.message) || t('order_error'));
        err.code = data.error && data.error.code;
        throw err;
      }
      // the server answers with the admin's current number: always use it
      if (data.whatsapp) applyPhone(data.whatsapp);
      const href = 'https://wa.me/' + WHATSAPP_NUMBER + '?text=' + encodeURIComponent(waMessage(data, c));
      if (win && !win.closed) win.location.href = href; else window.location.href = href;
      cart = [];
      saveCart();
      ['#checkoutAddress', '#checkoutLocation'].forEach((s) => { $(s).value = ''; });
      renderCart();
      closeCart();
      toast(t('order_success'));
      return true;
    } catch (err) {
      if (win && !win.closed) win.close();
      if (err.code === 'product_unavailable' || err.code === 'invalid_size') {
        await loadCatalog();
        renderCatalog();
        toast(t('cart_refreshed'));
      } else {
        toast(err.message || t('order_error'));
      }
      return false;
    } finally {
      btn.disabled = false;
    }
  }

  function locate() {
    if (!navigator.geolocation) { toast(t('location_fail')); return; }
    toast(t('locating'));
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords;
        $('#checkoutLocation').value = 'https://maps.google.com/?q=' + latitude.toFixed(6) + ',' + longitude.toFixed(6);
        toast(t('location_ok'));
      },
      () => toast(t('location_fail')),
      { enableHighAccuracy: true, timeout: 10000 }
    );
  }

  /* ---------- toasts ---------- */
  function toast(msg) {
    const box = $('#toasts');
    const el = document.createElement('div');
    el.className = 'toast';
    el.innerHTML = '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="M20 6 9 17l-5-5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    el.appendChild(document.createTextNode(msg));
    box.appendChild(el);
    while (box.children.length > 3) box.firstChild.remove();
    setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 300); }, 3200);
  }

  /* ---------- search ---------- */
  /* Live search: results appear under the search box while typing (no button
     needed), as a list of rows: image, name, price. The server ranks them
     (Meilisearch: Arabic / French / English, typo tolerant); rows are drawn
     from the catalog already loaded. If the API cannot be reached, a simple
     local match keeps search usable. */
  let searchTimer = 0;
  let searchSeq = 0;
  let searchHits = [];
  let searchActive = -1;
  const foldText = (x) => String(x || '').toLowerCase().normalize('NFKD')
    .replace(/[\u0300-\u036f\u064b-\u065f\u0670\u0640]/g, '')
    .replace(/[أإآٱ]/g, 'ا').replace(/ة/g, 'ه').replace(/ى/g, 'ي');

  function localSearch(q) {
    const words = foldText(q).split(/\s+/).filter(Boolean);
    return allProducts().filter((p) => {
      const hay = foldText([p.name, p.name_fr, p.name_en, p.description].join(' '));
      return words.every((w) => hay.indexOf(w.replace(/^(وال|بال|ال)/, '')) !== -1);
    });
  }

  function setSearchOpen(open) {
    $('#searchResults').hidden = !open;
    $('#searchInput').setAttribute('aria-expanded', String(open));
    if (!open) setActive(-1);
  }
  const closeSearch = () => setSearchOpen(false);

  function setActive(i) {
    searchActive = i;
    $$('#searchResults .sr-item').forEach((el, j) => {
      el.classList.toggle('active', j === i);
      el.setAttribute('aria-selected', String(j === i));
      if (j === i) el.scrollIntoView({ block: 'nearest' });
    });
    const input = $('#searchInput');
    if (i >= 0) input.setAttribute('aria-activedescendant', 'sr-' + i);
    else input.removeAttribute('aria-activedescendant');
  }

  function showResults(q, hits) {
    searchHits = hits.slice(0, 12);
    const box = $('#searchResults');
    box.innerHTML = searchHits.length
      ? searchHits.map((p, i) =>
        '<li class="sr-item" role="option" id="sr-' + i + '" data-id="' + esc(p.id) + '" aria-selected="false">' +
        '<img src="' + esc(p.img || catImg(p.cat)) + '" alt="" loading="lazy" width="46" height="46">' +
        '<span class="sr-name">' + esc(p.name) + '</span>' +
        '<span class="sr-price">' + esc(priceLabel(p)) + '</span></li>').join('')
      : '<li class="sr-empty" role="presentation">' + esc(t('no_results', q)) + '</li>';
    setSearchOpen(true);
    setActive(-1);
  }

  function runSearch(query, seq) {
    fetch('/api/v1/search?q=' + encodeURIComponent(query) + '&limit=12', { cache: 'no-store' })
      .then((r) => { if (!r.ok) throw new Error('api'); return r.json(); })
      .then((data) => {
        if (seq !== searchSeq) return; // a newer keystroke won
        const byId = {};
        allProducts().forEach((p) => { byId[p.id] = p; });
        showResults(query, (data.ids || []).map((id) => byId[id]).filter(Boolean));
      })
      .catch(() => { if (seq === searchSeq) showResults(query, localSearch(query)); });
  }

  function doSearch(q, now) {
    const query = (q || '').trim();
    clearTimeout(searchTimer);
    const seq = ++searchSeq;
    if (!query) { closeSearch(); return; }
    if (now) runSearch(query, seq);
    else searchTimer = setTimeout(() => runSearch(query, seq), 150);
  }

  function pickResult(i) {
    const p = searchHits[i];
    if (!p) return;
    closeSearch();
    $('#searchInput').blur();
    openDetails(p.id);
  }

  function initSearch() {
    const input = $('#searchInput');
    const box = $('#searchResults');
    input.addEventListener('input', () => doSearch(input.value));
    input.addEventListener('focus', () => { if (input.value.trim() && box.innerHTML) setSearchOpen(true); });
    input.addEventListener('keydown', (e) => {
      const open = !box.hidden && searchHits.length;
      if (e.key === 'ArrowDown' && open) { e.preventDefault(); setActive((searchActive + 1) % searchHits.length); }
      else if (e.key === 'ArrowUp' && open) { e.preventDefault(); setActive(searchActive <= 0 ? searchHits.length - 1 : searchActive - 1); }
      else if (e.key === 'Enter') {
        e.preventDefault();
        if (open) pickResult(searchActive >= 0 ? searchActive : 0);
        else doSearch(input.value, true);
      }
    });
    // keep focus in the box while clicking a row, then open the product
    box.addEventListener('mousedown', (e) => e.preventDefault());
    box.addEventListener('click', (e) => {
      const row = e.target.closest('.sr-item');
      if (row) pickResult(Number(row.id.slice(3)));
    });
    box.addEventListener('mousemove', (e) => {
      const row = e.target.closest('.sr-item');
      if (row && Number(row.id.slice(3)) !== searchActive) setActive(Number(row.id.slice(3)));
    });
    $('#searchBtn').addEventListener('click', () => { input.focus(); doSearch(input.value, true); });
    document.addEventListener('click', (e) => { if (!e.target.closest('.search')) closeSearch(); });
  }

  /* ---------- menus / drawers ---------- */
  function openCart() { $('#cartDrawer').classList.add('open'); $('#overlay').classList.add('show'); document.body.style.overflow = 'hidden'; }
  function closeCart() { $('#cartDrawer').classList.remove('open'); $('#overlay').classList.remove('show'); document.body.style.overflow = ''; }
  function openMenu() { $('#mobileMenu').classList.add('open'); document.body.style.overflow = 'hidden'; }
  function closeMenu() { $('#mobileMenu').classList.remove('open'); document.body.style.overflow = ''; }

  function initChrome() {
    const btn = $('#langBtn'), menu = $('#langMenu');
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const open = menu.classList.toggle('show');
      btn.setAttribute('aria-expanded', String(open));
    });
    $$('#langMenu .lang-item').forEach((item) => item.addEventListener('click', () => {
      setLang(item.dataset.lang);
      menu.classList.remove('show');
      btn.setAttribute('aria-expanded', 'false');
    }));
    $$('.footer-lang a').forEach((a) => a.addEventListener('click', (e) => { e.preventDefault(); setLang(a.dataset.lang); }));
    document.addEventListener('click', (e) => {
      if (!$('#langSelect').contains(e.target)) { menu.classList.remove('show'); btn.setAttribute('aria-expanded', 'false'); }
    });

    $('#menuBtn').addEventListener('click', openMenu);
    $('#closeMenu').addEventListener('click', closeMenu);
    $('#mobileMenu').addEventListener('click', (e) => { if (e.target.id === 'mobileMenu' || e.target.closest('a')) closeMenu(); });
    $('#openCart').addEventListener('click', openCart);
    $('#mobileCartBtn').addEventListener('click', () => { closeMenu(); openCart(); });
    $('#closeCart').addEventListener('click', closeCart);
    $('#overlay').addEventListener('click', closeCart);
    $('#cartItems').addEventListener('click', onCartClick);

    initSearch();

    $('#pdClose').addEventListener('click', closeDetails);
    $('#productModal').addEventListener('click', (e) => { if (e.target.id === 'productModal') closeDetails(); });

    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape') return;
      closeCart(); closeSearch(); closeMenu(); closeDetails(); waBotClose();
    });

    // collapse/expand category sections + every product card interaction (delegated, bound once)
    document.addEventListener('click', (e) => {
      const head = e.target.closest('.cat-head');
      if (head) {
        const collapsed = head.closest('.cat-section').classList.toggle('collapsed');
        head.setAttribute('aria-expanded', String(!collapsed));
        return;
      }
      onCardClick(e);
    });

    $('#checkoutCity').addEventListener('input', renderTotals);
    $('#checkoutCity').addEventListener('change', () => {
      const el = $('#checkoutCity');
      if (window.Delivery) el.value = Delivery.normalizeCity(el.value);
      renderTotals();
    });
    $('#checkoutForm').addEventListener('input', (e) => e.target.removeAttribute('aria-invalid'));
    $('#checkoutForm').addEventListener('submit', (e) => { e.preventDefault(); placeOrder('online'); });
    $('#checkoutBtn').addEventListener('click', () => placeOrder('online'));
    $('#btnLocate').addEventListener('click', locate);

    $('#newsletterForm').addEventListener('submit', (e) => {
      e.preventDefault();
      const em = $('#newsletterEmail');
      const email = em.value.trim();
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(email)) { toast(t('newsletter_invalid')); em.focus(); return; }
      fetch('/api/v1/newsletter', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, lang: LANG }) })
        .then((r) => { if (!r.ok) throw new Error('api'); em.value = ''; toast(t('newsletter_ok')); })
        .catch(() => toast(t('newsletter_fail')));
    });
  }

  /* ---------- assistant (guided order, same server flow as the cart) ---------- */
  const BOT_T = {
    ar: {
      welcome: 'مرحباً بكم في فيه شفاء 🌿\nكيف يمكنني مساعدتكم؟', emptyCart: 'سلتك فارغة حالياً.\nأضف المنتجات التي تعجبك ثم ارجع لتأكيد الطلب.',
      cartHeader: 'في سلتك {n} منتج:', cartTotal: 'المجموع (بدون التوصيل): {t}',
      askName: 'ما هو اسمكم الكامل؟', askPhone: 'ما هو رقم هاتفكم؟', askCity: 'في أي مدينة تريدون التوصيل؟', askAddress: 'ما هو العنوان بالتفصيل (الشارع، الحي، رقم المنزل)؟',
      askConfirm: 'هل تريدون تأكيد الطلب الآن؟', confirmBtn: 'تأكيد الطلب ✅', viewCartBtn: 'عرض السلة 🛒', deliveryBtn: 'معلومات التوصيل 🚚', productsBtn: 'تصفح المنتجات 🍯',
      yes: 'نعم، تأكيد', no: 'إلغاء', thanks: 'شكراً! تم تسجيل طلبكم ✅ وتم فتح واتساب لإرساله إلى البائع.',
      fallback: 'لم أفهم تماماً. اختر من الأزرار أو اكتب: تأكيد، سلة، توصيل.',
      deliveryInfo: 'التوصيل مجاني داخل البهاليل دائماً، ومجاني لباقي المدن ابتداءً من 500 درهم، وإلا 40 درهم. نوصل لجميع أنحاء المغرب خلال 24 إلى 72 ساعة، والدفع عند الاستلام.',
      invalidPhone: 'يرجى إدخال رقم هاتف صحيح (8 أرقام على الأقل).', needText: 'يرجى كتابة إجابة أوضح.', orderEmpty: 'لا يمكن تأكيد طلب فارغ.',
    },
    fr: {
      welcome: 'Bienvenue chez fihi-chifae 🌿\nComment puis-je vous aider ?', emptyCart: 'Votre panier est vide.\nAjoutez des produits puis revenez confirmer.',
      cartHeader: 'Votre panier contient {n} article(s) :', cartTotal: 'Total (hors livraison) : {t}',
      askName: 'Quel est votre nom complet ?', askPhone: 'Quel est votre numéro de téléphone ?', askCity: 'Dans quelle ville livrer ?', askAddress: 'Quelle est votre adresse (rue, quartier, n°) ?',
      askConfirm: 'Voulez-vous confirmer la commande ?', confirmBtn: 'Confirmer ✅', viewCartBtn: 'Voir panier 🛒', deliveryBtn: 'Livraison 🚚', productsBtn: 'Produits 🍯',
      yes: 'Oui, confirmer', no: 'Annuler', thanks: 'Merci ! Commande enregistrée ✅ WhatsApp est ouvert pour l’envoyer au vendeur.',
      fallback: "Je n'ai pas compris. Choisissez un bouton ou écrivez : confirmer, panier, livraison.",
      deliveryInfo: 'Livraison toujours gratuite à BHALIL, gratuite ailleurs dès 500 MAD, sinon 40 MAD. Partout au Maroc en 24 à 72 h, paiement à la livraison.',
      invalidPhone: 'Veuillez saisir un numéro valide (au moins 8 chiffres).', needText: 'Merci de préciser votre réponse.', orderEmpty: 'Impossible de confirmer un panier vide.',
    },
    en: {
      welcome: 'Welcome to fihi-chifae 🌿\nHow can I help you?', emptyCart: 'Your cart is empty.\nAdd products and come back to confirm.',
      cartHeader: 'You have {n} item(s) in your cart:', cartTotal: 'Total (before delivery): {t}',
      askName: 'What is your full name?', askPhone: 'What is your phone number?', askCity: 'Which city should we deliver to?', askAddress: 'What is your address (street, area, number)?',
      askConfirm: 'Do you want to confirm the order?', confirmBtn: 'Confirm ✅', viewCartBtn: 'View cart 🛒', deliveryBtn: 'Delivery 🚚', productsBtn: 'Products 🍯',
      yes: 'Yes, confirm', no: 'Cancel', thanks: 'Thank you! Order recorded ✅ WhatsApp is open to send it to the seller.',
      fallback: 'Sorry, I did not understand. Choose a button or type: confirm, cart, delivery.',
      deliveryInfo: 'Delivery is always free in BHALIL, free elsewhere from 500 MAD, otherwise 40 MAD. All over Morocco in 24–72 h, cash on delivery.',
      invalidPhone: 'Please enter a valid phone (at least 8 digits).', needText: 'Please give a clearer answer.', orderEmpty: 'Cannot confirm an empty cart.',
    },
  };
  const bot = () => BOT_T[LANG] || BOT_T.ar;
  const STEPS = [
    { field: '#checkoutName', ask: 'askName', check: (v) => v.length >= 2 },
    { field: '#checkoutPhone', ask: 'askPhone', check: (v) => v.replace(/\D/g, '').length >= 8, error: 'invalidPhone' },
    { field: '#checkoutCity', ask: 'askCity', check: (v) => v.length >= 2 },
    { field: '#checkoutAddress', ask: 'askAddress', check: (v) => v.length >= 4 },
  ];
  let botStep = null; // index in STEPS, 'confirm' or null
  let botOpened = false;

  const botTime = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  function botMsg(text, who, quicks) {
    const box = $('#waBotMessages');
    const div = document.createElement('div');
    div.className = 'wa-msg ' + who;
    div.innerHTML = esc(text).replace(/\n/g, '<br>') + '<small>' + botTime() + '</small>';
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
    if (who === 'bot') botQuick(quicks);
  }
  function botQuick(quicks) {
    const q = $('#waBotQuick');
    q.innerHTML = '';
    (quicks || []).forEach((o) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'wa-quick-btn';
      b.textContent = o.label;
      b.addEventListener('click', () => botHandle(o.value, o.label));
      q.appendChild(b);
    });
  }
  function cartSummary() {
    const b = bot();
    if (!cart.length) return b.emptyCart;
    return b.cartHeader.replace('{n}', cartCount()) + '\n' +
      cart.map((it) => '• ' + it.qty + ' × ' + it.name + (it.size ? ' (' + sizeText(it.size) + ')' : '')).join('\n') + '\n' +
      b.cartTotal.replace('{t}', money(cartSubtotal()));
  }
  function defaultQuicks() {
    const b = bot();
    return cart.length
      ? [{ label: b.confirmBtn, value: 'confirm' }, { label: b.viewCartBtn, value: 'cart' }, { label: b.deliveryBtn, value: 'delivery' }]
      : [{ label: b.productsBtn, value: 'products' }, { label: b.deliveryBtn, value: 'delivery' }];
  }
  function nextStep() {
    const idx = STEPS.findIndex((s) => !s.check($(s.field).value.trim()));
    if (idx === -1) {
      botStep = 'confirm';
      botMsg(cartSummary() + '\n\n' + bot().askConfirm, 'bot', [{ label: bot().yes, value: 'yes' }, { label: bot().no, value: 'no' }]);
    } else {
      botStep = idx;
      botMsg(bot()[STEPS[idx].ask], 'bot', []);
    }
  }
  async function botHandle(value, label) {
    const raw = String(value || '').trim();
    if (!raw) return;
    const b = bot();
    botMsg(label || raw, 'user');
    if (typeof botStep === 'number') {
      const step = STEPS[botStep];
      if (!step.check(raw)) { botMsg(b[step.error || 'needText'], 'bot', []); return; }
      $(step.field).value = step.field === '#checkoutCity' && window.Delivery ? Delivery.normalizeCity(raw) : raw;
      renderTotals();
      setTimeout(nextStep, 250);
      return;
    }
    const norm = raw.toLowerCase();
    if (botStep === 'confirm') {
      botStep = null;
      if (/^(yes|نعم|oui|confirm)/.test(norm)) {
        if (await placeOrder('chatbot')) botMsg(b.thanks, 'bot', []);
        else botMsg(b.fallback, 'bot', defaultQuicks());
      } else {
        botMsg(b.fallback, 'bot', defaultQuicks());
      }
      return;
    }
    if (/confirm|تأكيد|تاكيد|confirmer/.test(norm)) {
      if (!cart.length) { botMsg(b.orderEmpty, 'bot', defaultQuicks()); return; }
      nextStep();
      return;
    }
    if (/cart|panier|سلة|عرض/.test(norm)) { botMsg(cartSummary(), 'bot', defaultQuicks()); return; }
    if (/deliver|livraison|توصيل/.test(norm)) { botMsg(b.deliveryInfo, 'bot', defaultQuicks()); return; }
    if (/product|produit|منتج|عسل|miel|honey/.test(norm)) { waBotClose(); document.getElementById('featured').scrollIntoView({ behavior: 'smooth' }); return; }
    botMsg(b.fallback, 'bot', defaultQuicks());
  }
  function waBotOpen() {
    closeCart();
    const ov = $('#waBotOverlay');
    ov.classList.add('open');
    ov.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    if (!botOpened) { botOpened = true; botMsg(bot().welcome + '\n\n' + cartSummary(), 'bot', defaultQuicks()); }
    setTimeout(() => $('#waBotInput').focus(), 200);
  }
  function waBotClose() {
    const ov = $('#waBotOverlay');
    if (!ov.classList.contains('open')) return;
    ov.classList.remove('open');
    ov.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    botStep = null;
  }
  function initAssistant() {
    $('#waBtn').addEventListener('click', waBotOpen);
    $('#waBotClose').addEventListener('click', waBotClose);
    $('#waBotOverlay').addEventListener('click', (e) => { if (e.target.id === 'waBotOverlay') waBotClose(); });
    const send = () => { const v = $('#waBotInput').value.trim(); $('#waBotInput').value = ''; botHandle(v); };
    $('#waBotSend').addEventListener('click', send);
    $('#waBotInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); send(); } });
  }

  /* ---------- init ---------- */
  document.addEventListener('DOMContentLoaded', () => {
    try { const l = localStorage.getItem('dhenbio_lang'); if (l && T[l]) LANG = l; } catch (e) { /* ignore */ }
    initChrome();
    initAssistant();
    applyI18n(); // first paint in the visitor's language
    loadCatalog().then(() => {
      // keep cart lines in sync with the current catalog (removed products disappear)
      if (loaded) {
        const ids = new Set(allProducts().map((p) => p.id));
        const before = cart.length;
        cart = cart.filter((it) => !it.id || ids.has(it.id));
        if (cart.length !== before) { saveCart(); toast(t('cart_refreshed')); }
      }
      renderCatalog();
      renderCart();
    });
  });
})();
