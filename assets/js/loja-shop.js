/**
 * GeoVision Shop (loja.js)
 * 
 * Integração completa com backend /shop API:
 *  - Catálogo de produtos (/shop/products)
 *  - Carrinho (/shop/cart)
 *  - Checkout com 4 métodos de pagamento
 *  - Tracking de pedidos
 */

const API_URL = window.API_BASE;

/* HTML escaping utility (XSS prevention) */
const esc = window.escapeHTML || (s => { const d = document.createElement('div'); d.textContent = String(s == null ? '' : s); return d.innerHTML; });

// Estado da loja
let allProducts = [];
let cartId = localStorage.getItem("gv_cart_id") || generateCartId();
let currentCart = null;
const MARKETPLACE_SECTOR_KEY = "gv_marketplace_sector";
const STORE_SECTORS = new Set(["agro", "environment", "construction", "infrastructure"]);
function normalizeStoreSector(value) {
  if (["ambiental"].includes(value)) return "environment";
  if (value === "livestock") return "agro";
  return STORE_SECTORS.has(value) ? value : null;
}
const recommendedSector = normalizeStoreSector(localStorage.getItem(MARKETPLACE_SECTOR_KEY));
const requestedSector = new URLSearchParams(window.location.search).get("sector");
let currentSectorFilter = normalizeStoreSector(requestedSector) || recommendedSector || "all";

const PRODUCT_PUBLIC_COPY = {
  prod_kit_water_tank_starter: { name: "GV Level — Água & Bomba", desc: "Acompanhe nível do depósito, caudal e funcionamento da bomba, com alertas configuráveis." },
  prod_kit_agri_field_node: { name: "GV Soil — Nó Agrícola Solar", desc: "Solo, temperatura, humidade e chuva num nó de campo; configuração final por local." },
  prod_kit_facility_guard: { name: "GV Site — Propriedade & Fugas", desc: "Porta, movimento e deteção de água para propriedades pequenas, com histórico e alertas." },
  prod_kit_environment_air: { name: "GV Air — Ambiente & Conforto", desc: "CO₂, partículas, temperatura, humidade e ruído para espaços interiores ou exteriores." },
  prod_kit_gps_asset_tracker: { name: "GV Track — Ativos Móveis", desc: "Localização, movimento, bateria e sinal para ativos compatíveis." },
  prod_kit_soil_control: { name: "GV SoilControl — Rega Monitorizada", desc: "Solo, nível e caudal com opção de válvula de baixa tensão, sujeito a validação de instalação." },
  prod_kit_agro_weather: { name: "GV AgroWeather — Estação de Campo", desc: "Temperatura, humidade, pressão, chuva, vento e radiação para apoio ao trabalho agrícola." },
  prod_kit_greenhouse_control: { name: "GV Greenhouse — Clima de Estufa", desc: "Clima, substrato, CO₂ e luz, com controlo opcional de baixa tensão." },
  prod_kit_input_track: { name: "GV InputTrack — Insumos & Ativos", desc: "Localização e nível de stock para apoiar registos de equipamento e reposição." },
};
let currentTypeFilter = "all";
let pendingAddProduct = null;
let stripeInstance = null;
let stripeElements = null;

// Sector labels for display
const SECTOR_LABEL_KEYS = {
  "environment": "loja.sector.environment",
  "construction": "loja.sector.construction",
  "infrastructure": "loja.sector.infrastructure",
  "agro": "loja.sector.agro",
};
const storeT = (key) => (window.t && window.t(key)) || key;
const storeFormat = (key, values = {}) => Object.entries(values).reduce(
  (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
  storeT(key),
);
const storeSectorLabel = (sector) =>
  SECTOR_LABEL_KEYS[normalizeStoreSector(sector)]
    ? storeT(SECTOR_LABEL_KEYS[normalizeStoreSector(sector)])
    : (sector || "—");

// Guardar cartId no localStorage
function generateCartId() {
  const id = "cart_" + Math.random().toString(36).substring(2, 15);
  localStorage.setItem("gv_cart_id", id);
  return id;
}

// ============ FORMATAÇÃO ============

let selectedCurrency = "AOA";

function formatPrice(cents, currency) {
  const cur = currency || selectedCurrency || "AOA";
  const value = cents / 100;
  const locales = { AOA: "pt-AO", USD: "en-US", EUR: "pt-PT" };
  return value.toLocaleString(locales[cur] || "pt-AO", {
    style: "currency", currency: cur,
    minimumFractionDigits: cur === "AOA" ? 0 : 2,
    maximumFractionDigits: cur === "AOA" ? 0 : 2,
  });
}

function formatAOA(cents) {
  return formatPrice(cents, selectedCurrency);
}

function formatAOASimple(cents) {
  return formatPrice(cents, selectedCurrency);
}

/** Get the correct price for a product based on selected currency */
function getProductPrice(product) {
  if (selectedCurrency === 'USD' && product.price_usd) return product.price_usd;
  if (selectedCurrency === 'EUR' && product.price_eur) return product.price_eur;
  return product.price; // AOA default
}

// ============ CURRENCY / PAYMENT TOGGLE ============

// Only offer payment methods that actually settle in this deployment. Bank/IBAN
// transfer always works; gateway methods appear only when their credentials are
// configured (otherwise they would silently mock). null = not yet loaded (allow all).
let enabledPaymentMethods = null;
function paymentEnabled(method) {
  return !enabledPaymentMethods || enabledPaymentMethods.has(method);
}
async function loadPaymentMethods() {
  try {
    const res = await fetch(`${API_BASE}/shop/payment-methods`);
    if (!res.ok) return;
    const data = await res.json();
    enabledPaymentMethods = new Set((data.methods || []).filter((m) => m.enabled).map((m) => m.method));
    onCurrencyChange(selectedCurrency || 'AOA');
  } catch (_) { /* leave all methods available on error */ }
}

async function onCurrencyChange(currency) {
  selectedCurrency = currency;
  // Show/hide payment methods based on currency AND real availability
  document.querySelectorAll('.payment-option[data-currencies]').forEach(el => {
    const currencies = el.getAttribute('data-currencies').split(',');
    const method = el.querySelector('input[type="radio"]')?.value;
    if (currencies.includes(currency) && paymentEnabled(method)) {
      el.style.display = 'flex';
    } else {
      el.style.display = 'none';
      // Uncheck hidden radios
      const radio = el.querySelector('input[type="radio"]');
      if (radio) radio.checked = false;
    }
  });
  // Auto-select first visible payment method
  const firstVisible = document.querySelector('.payment-option[data-currencies]:not([style*="display: none"]) input[type="radio"]');
  if (firstVisible) {
    firstVisible.checked = true;
    selectPayment(firstVisible.value);
  }
  // Re-render product cards with correct prices
  renderProducts();
  // Update cart prices on the backend when currency changes
  if (currentCart && currentCart.items && currentCart.items.length > 0) {
    try {
      const res = await fetch(`${API_URL}/shop/cart/${cartId}/currency`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ currency }),
      });
      if (res.ok) {
        currentCart = await res.json();
      }
    } catch (err) {
      console.error("Erro ao atualizar moeda do carrinho:", err);
    }
  }
  // Re-render cart and checkout summary AFTER backend update
  renderCart();
  renderCheckoutSummary();
}

// ============ CARREGAR PRODUTOS ============

async function loadProducts() {
  try {
    const res = await fetch(`${API_URL}/shop/products`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    
    allProducts = await res.json();
    renderProducts("all");
  } catch (err) {
    console.error("Erro ao carregar produtos:", err);
    const empty = document.getElementById("loja-empty");
    if (empty) {
      empty.style.display = "block";
      empty.textContent = storeT("loja.cart.loadError");
    }
  }
}

// ============ CARREGAR CARRINHO ============

async function loadCart() {
  try {
    const res = await fetch(`${API_URL}/shop/cart/${cartId}`);
    if (!res.ok) throw new Error("Falha ao carregar carrinho");
    
    currentCart = await res.json();
    renderCart();
  } catch (err) {
    console.error("Erro ao carregar carrinho:", err);
    currentCart = { items: [], total: 0, item_count: 0 };
    renderCart();
  }
}

// ============ RENDER CARRINHO ============

function renderCart() {
  const list = document.getElementById("cart-items");
  const countEl = document.getElementById("cart-count");
  const subtotalEl = document.getElementById("cart-subtotal");
  const discountEl = document.getElementById("cart-discount");
  const discountRow = document.getElementById("discount-row");
  const taxEl = document.getElementById("cart-tax");
  const taxRow = document.getElementById("tax-row");
  const totalEl = document.getElementById("cart-total");
  const couponStatus = document.getElementById("coupon-status");
  const multiTotalEl = document.getElementById("cart-multi-total");

  if (!list || !countEl || !totalEl) return;

  list.innerHTML = "";

  if (!currentCart || !currentCart.items.length) {
    const empty = document.createElement("div");
    empty.className = "loja-empty";
    empty.textContent = storeT("loja.cart.empty");
    list.appendChild(empty);
    countEl.textContent = "0 itens";
    if (subtotalEl) subtotalEl.textContent = formatAOA(0);
    if (discountRow) discountRow.style.display = "none";
    if (taxRow) taxRow.style.display = "none";
    totalEl.textContent = formatAOA(0);
    if (multiTotalEl) multiTotalEl.style.display = "none";
    if (couponStatus) couponStatus.style.display = "none";
    return;
  }

  currentCart.items.forEach((item) => {
    // Find the product to get multi-currency prices
    const product = allProducts.find(p => p.id === item.product_id);
    const itemName = product ? localizedProductCopy(product).name : item.product_name;
    const row = document.createElement("div");
    row.className = "loja-cart-item";
    row.innerHTML = `
      <div>
        <div class="loja-cart-item-name">${esc(itemName)}</div>
        <div class="loja-cart-item-meta">
          ${item.quantity} × ${formatAOASimple(item.unit_price)}
        </div>
      </div>
      <div class="loja-cart-item-actions">
        <div class="qty-stepper">
          <button class="qty-minus" onclick="updateCartQty('${esc(item.id)}', ${item.quantity - 1})" title="${esc(storeT('loja.cart.removeOne'))}">−</button>
          <span class="qty-val">${item.quantity}</span>
          <button class="qty-plus" onclick="updateCartQty('${esc(item.id)}', ${item.quantity + 1})" title="${esc(storeT('loja.cart.addOne'))}">+</button>
        </div>
        <button class="cart-remove-btn" onclick="removeFromCart('${esc(item.id)}')" title="${esc(storeT('loja.cart.remove'))}">
          ✕
        </button>
      </div>
    `;
    list.appendChild(row);
  });

  const countLabel = currentCart.item_count === 1
    ? `1 ${storeT("loja.cart.item")}`
    : `${currentCart.item_count} ${storeT("loja.cart.items")}`;
  countEl.textContent = countLabel;
  
  // Update subtotal
  if (subtotalEl) {
    subtotalEl.textContent = formatAOA(currentCart.subtotal || currentCart.total);
  }
  
  // Update discount
  if (discountRow && discountEl) {
    if (currentCart.discount_amount > 0) {
      discountRow.style.display = "flex";
      discountEl.textContent = "-" + formatAOA(currentCart.discount_amount);
      if (couponStatus && currentCart.coupon_code) {
        couponStatus.textContent = storeFormat("loja.cart.couponApplied", { code: currentCart.coupon_code });
        couponStatus.style.display = "block";
      }
    } else {
      discountRow.style.display = "none";
      if (couponStatus) couponStatus.style.display = "none";
    }
  }
  
  // Show IVA as included (not added on top)
  if (taxRow && taxEl) {
    if (currentCart.tax_amount > 0) {
      taxRow.style.display = "flex";
      taxEl.textContent = formatAOA(currentCart.tax_amount);
    } else {
      taxRow.style.display = "none";
    }
  }
  
  // Update main total (IVA already included in subtotal)
  totalEl.textContent = formatAOA(currentCart.total);

  // Compute and show all 3 currency totals
  if (multiTotalEl) {
    const totals = computeMultiCurrencyTotals();
    multiTotalEl.innerHTML = `
      <div class="multi-total-row"><span class="cur-badge cur-aoa">AOA</span> ${formatPrice(totals.aoa, 'AOA')}</div>
      <div class="multi-total-row"><span class="cur-badge cur-usd">USD</span> ${formatPrice(totals.usd, 'USD')}</div>
      <div class="multi-total-row"><span class="cur-badge cur-eur">EUR</span> ${formatPrice(totals.eur, 'EUR')}</div>
    `;
    multiTotalEl.style.display = "block";
  }
}

/** Compute cart totals in all 3 currencies using admin-defined prices */
function computeMultiCurrencyTotals() {
  const totals = { aoa: 0, usd: 0, eur: 0 };
  if (!currentCart || !currentCart.items) return totals;

  currentCart.items.forEach(item => {
    const product = allProducts.find(p => p.id === item.product_id);
    if (product) {
      totals.aoa += product.price * item.quantity;
      totals.usd += (product.price_usd || 0) * item.quantity;
      totals.eur += (product.price_eur || 0) * item.quantity;
    } else {
      // Fallback: use cart item unit_price for selected currency
      totals.aoa += item.total_price;
    }
  });

  // Prices already include IVA — no tax multiplication needed
  return totals;
}

// ============ ADICIONAR AO CARRINHO ============

async function handleAddToCart(productId) {
  // Check for sector mismatch before adding
  try {
    const res = await fetch(`${API_URL}/shop/check-sector-mismatch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cart_id: cartId,
        product_id: productId,
        account_sector: recommendedSector,
      }),
    });

    if (res.ok) {
      const data = await res.json();
      if (data.warning) {
        // Show warning modal but don't block
        pendingAddProduct = productId;
        showSectorWarning(data);
        return;
      }
    }
  } catch (err) {
    // If check fails, proceed anyway (non-blocking)
    console.warn("Sector mismatch check failed:", err);
  }

  // No mismatch or check failed - proceed with add
  await addToCart(productId);
}

function showSectorWarning(data) {
  const modal = document.getElementById("sector-warning-modal");
  const msgEl = document.getElementById("sector-warning-message");
  
  if (!modal || !msgEl) return;
  
  const productSectorLabel = storeSectorLabel(data.product_sector);
  const accountSectorLabel = storeSectorLabel(data.account_sector);
  msgEl.textContent = storeFormat("loja.sectorWarning.detail", {
    product: productSectorLabel,
    account: accountSectorLabel,
  });
  
  modal.style.display = "flex";
}

function closeSectorWarning() {
  const modal = document.getElementById("sector-warning-modal");
  if (modal) modal.style.display = "none";
  pendingAddProduct = null;
}

async function continueAddToCart() {
  const productId = pendingAddProduct;
  closeSectorWarning();
  if (productId) {
    await addToCart(productId);
  }
}

function redirectToCreateAccount() {
  closeSectorWarning();
  window.location.href = "login.html?mode=register&return=loja.html";
}

async function addToCart(productId) {
  try {
    const res = await fetch(`${API_URL}/shop/cart/${cartId}/items`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        product_id: productId,
        quantity: 1,
        currency: selectedCurrency,
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Erro ao adicionar item");
    }

    currentCart = await res.json();
    renderCart();
    
    // Feedback visual
    showToast(`Adicionado ao carrinho!`);
  } catch (err) {
    console.error("Erro ao adicionar ao carrinho:", err);
    alert(err.message);
  }
}

// ============ ATUALIZAR QUANTIDADE ============

async function updateCartQty(itemId, newQty) {
  if (newQty <= 0) {
    return removeFromCart(itemId);
  }
  try {
    const res = await fetch(`${API_URL}/shop/cart/${cartId}/items/${itemId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ quantity: newQty }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Erro ao atualizar quantidade");
    }
    currentCart = await res.json();
    renderCart();
  } catch (err) {
    console.error("Erro ao atualizar quantidade:", err);
    alert(err.message);
  }
}

// ============ REMOVER DO CARRINHO ============

async function removeFromCart(itemId) {
  try {
    const res = await fetch(`${API_URL}/shop/cart/${cartId}/items/${itemId}`, {
      method: "DELETE",
    });

    if (!res.ok) throw new Error("Erro ao remover item");

    currentCart = await res.json();
    renderCart();
  } catch (err) {
    console.error("Erro ao remover do carrinho:", err);
    alert(err.message);
  }
}

// ============ LIMPAR CARRINHO ============

async function clearCart() {
  try {
    await fetch(`${API_URL}/shop/cart/${cartId}`, {
      method: "DELETE",
    });

    currentCart = { items: [], total: 0, item_count: 0 };
    renderCart();
  } catch (err) {
    console.error("Erro ao limpar carrinho:", err);
  }
}

// ============ APLICAR CUPÃO ============

async function applyCoupon() {
  const code = document.getElementById("coupon-input")?.value?.trim();
  if (!code) {
    alert("Introduz um código de cupão");
    return;
  }

  try {
    const res = await fetch(`${API_URL}/shop/cart/${cartId}/coupon`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Cupão inválido");
    }

    currentCart = await res.json();
    renderCart();
    showToast("Cupão aplicado!");
  } catch (err) {
    alert(err.message);
  }
}

// ============ RENDER PRODUTOS ============

function mapCategoryLabel(category) {
  const mapping = {
    "analysis": "loja.category.analysis",
    "mapping": "loja.category.mapping",
    "spraying": "loja.category.spraying",
    "monitoring": "loja.category.monitoring",
    "flight": "loja.category.flight",
    "sensor_kit": "loja.category.sensorKit",
    "sensor": "loja.category.sensor",
    "irrigation": "loja.category.irrigation",
    "accessory": "loja.category.accessory",
  };
  return mapping[category] ? storeT(mapping[category]) : (category || storeT("loja.category.service"));
}

function localizedProductCopy(product) {
  const lang = window.i18n?.getCurrentLanguage?.() || localStorage.getItem('gv_lang') || 'pt';
  const localized = product.translations?.[lang] || product.translations?.pt || {};
  const fallback = PRODUCT_PUBLIC_COPY[product.id] || {};
  return {
    name: localized.name || fallback.name || product.name,
    description: localized.short_description || localized.description || fallback.desc ||
      product.short_description || product.description || storeT("loja.productFallback"),
    deliverables: localized.deliverables || product.deliverables || [],
  };
}

function mapFilterKey(product) {
  const type = product.product_type;
  if (type === "service") return "servico";
  if (type === "subscription") return "subscription";
  if (type === "hardware") return "hardware";
  return "servico";
}

function getSectorBadgeClass(sector) {
  return `sector-badge ${sector}`;
}

function renderProducts() {
  const grid = document.getElementById("loja-grid");
  const empty = document.getElementById("loja-empty");

  if (!grid || !empty) return;

  grid.innerHTML = "";

  let filtered = [...allProducts];
  
  // Apply sector filter
  if (currentSectorFilter !== "all") {
    filtered = filtered.filter((p) => (p.sectors || []).some((s) => normalizeStoreSector(s) === currentSectorFilter));
  }
  filtered = filtered.filter((p) => (p.sectors || []).some((s) => normalizeStoreSector(s)));
  
  // Apply type filter
  if (currentTypeFilter !== "all") {
    filtered = filtered.filter((p) => mapFilterKey(p) === currentTypeFilter);
  }

  if (!filtered.length) {
    empty.style.display = "block";
    return;
  }
  empty.style.display = "none";

  // Put solutions for the active account first, then globally featured items.
  filtered.sort((a, b) => {
    const aRecommended = recommendedSector && (a.sectors || []).some((s) => normalizeStoreSector(s) === recommendedSector);
    const bRecommended = recommendedSector && (b.sectors || []).some((s) => normalizeStoreSector(s) === recommendedSector);
    if (aRecommended && !bRecommended) return -1;
    if (!aRecommended && bRecommended) return 1;
    if (a.is_featured && !b.is_featured) return -1;
    if (!a.is_featured && b.is_featured) return 1;
    return 0;
  });

  filtered.forEach((p) => {
    const card = document.createElement("article");
    card.className = "loja-card";

    const catLabel = mapCategoryLabel(p.category);
    const productCopy = localizedProductCopy(p);
    
    // Sector badges
    const publicSectors = [...new Set((p.sectors || []).map(normalizeStoreSector).filter(Boolean))];
    const sectorBadges = publicSectors.map(s => `<span class="${getSectorBadgeClass(s)}">${esc(SECTOR_LABEL_KEYS[s] ? storeT(SECTOR_LABEL_KEYS[s]) : s)}</span>`).join("");

    // Execution type badge
    const execBadge = p.execution_type 
      ? `<span class="execution-badge ${esc(p.execution_type)}">${storeT(p.execution_type === 'pontual' ? 'loja.execution.oneOff' : 'loja.execution.recurring')}</span>`
      : '';

    // Meta info
    let metaHtml = '';
    if (p.duration_hours) {
      metaHtml += `<span>⏱️ ${Number(p.duration_hours)}h</span>`;
    }
    if (p.min_area_ha) {
      metaHtml += `<span><i class="fa-solid fa-ruler-combined"></i> Min ${Number(p.min_area_ha)}ha</span>`;
    }

    // Deliverables preview
    let deliverablesHtml = '';
    if (productCopy.deliverables.length > 0) {
      const preview = productCopy.deliverables.slice(0, 3).map(d => esc(d)).join(", ");
      const more = productCopy.deliverables.length > 3 ? ` +${productCopy.deliverables.length - 3}` : '';
      deliverablesHtml = `<div class="deliverables-preview"><i class="fa-solid fa-box"></i> ${preview}${more}</div>`;
    }

    // Featured badge
    const featuredBadge = p.is_featured 
      ? `<span class="featured-badge">${esc(storeT("loja.featured"))}</span>`
      : '';
    const recommendationBadge = recommendedSector && publicSectors.includes(recommendedSector)
      ? `<span class="recommended-badge">${esc(storeT("loja.recommended"))}</span>`
      : '';

    card.innerHTML = `
      <div class="loja-card-badges">${recommendationBadge}${featuredBadge}</div>
      <div>
        <div class="loja-card-tag">${esc(catLabel)} ${execBadge}</div>
        <h3 class="loja-card-title">${esc(productCopy.name)}</h3>
        <p class="loja-card-desc">
          ${esc(productCopy.description)}
        </p>
        <div class="loja-card-sectors">${sectorBadges}</div>
        ${metaHtml ? `<div class="loja-card-meta">${metaHtml}</div>` : ''}
        ${deliverablesHtml}
      </div>
      <div class="loja-card-footer">
        <div class="loja-prices-multi">
          <div class="loja-price-row loja-price-aoa${selectedCurrency === 'AOA' ? ' active' : ''}">
            <span class="cur-badge cur-aoa">AOA</span>
            ${formatPrice(p.price, 'AOA')}${p.unit_label ? `<span class="unit">/${esc(p.unit_label)}</span>` : ""}
          </div>
          <div class="loja-price-row loja-price-usd${selectedCurrency === 'USD' ? ' active' : ''}">
            <span class="cur-badge cur-usd">USD</span>
            ${formatPrice(p.price_usd || 0, 'USD')}${p.unit_label ? `<span class="unit">/${esc(p.unit_label)}</span>` : ""}
          </div>
          <div class="loja-price-row loja-price-eur${selectedCurrency === 'EUR' ? ' active' : ''}">
            <span class="cur-badge cur-eur">EUR</span>
            ${formatPrice(p.price_eur || 0, 'EUR')}${p.unit_label ? `<span class="unit">/${esc(p.unit_label)}</span>` : ""}
          </div>
        </div>
        <button class="btn-add" onclick="handleAddToCart('${esc(p.id)}')">
          ${esc(storeT("loja.add"))}
        </button>
      </div>
    `;
    grid.appendChild(card);
  });
}

function updateStoreRecommendation() {
  const recommendation = document.getElementById("loja-account-recommendation");
  if (recommendation && recommendedSector) {
    recommendation.hidden = false;
    recommendation.textContent = `${storeT("loja.recommendedFor")} ${storeSectorLabel(recommendedSector)}`;
  }
}

window.addEventListener('gv:languagechange', () => {
  updateStoreRecommendation();
  renderProducts();
  renderCart();
  renderCheckoutSummary();
});

function setupFilters() {
  // Sector filter buttons (inside #sector-filters)
  const sectorButtons = document.querySelectorAll("#sector-filters .loja-filter-btn");
  const selectedSectorButton = [...sectorButtons].find((btn) => btn.getAttribute("data-sector") === currentSectorFilter);
  if (selectedSectorButton) {
    sectorButtons.forEach((button) => button.classList.remove("active"));
    selectedSectorButton.classList.add("active");
  } else {
    currentSectorFilter = "all";
  }
  updateStoreRecommendation();
  sectorButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      sectorButtons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentSectorFilter = btn.getAttribute("data-sector") || "all";
      renderProducts();
    });
  });

  // Type filter buttons (inside #type-filters)
  const typeButtons = document.querySelectorAll("#type-filters .loja-filter-btn");
  typeButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      typeButtons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentTypeFilter = btn.getAttribute("data-filter") || "all";
      renderProducts();
    });
  });
}

// ============ CHECKOUT ============

function isLoggedIn() {
  const token = localStorage.getItem("gv_token");
  return token && token.length > 10;
}

function getUserEmail() {
  return localStorage.getItem("gv_email") || "";
}

async function openCheckoutModal() {
  if (!currentCart || !currentCart.items.length) {
    alert(storeT("loja.cart.empty"));
    return;
  }

  const modal = document.getElementById("checkout-modal");
  const authChoice = document.getElementById("checkout-auth-choice");
  const checkoutContent = document.getElementById("checkout-content");
  
  if (!modal) return;
  
  modal.style.display = "flex";
  
  if (isLoggedIn()) {
    // User is logged in - skip auth choice, pre-fill email
    if (authChoice) authChoice.style.display = "none";
    if (checkoutContent) checkoutContent.style.display = "block";
    
    const emailInput = document.getElementById("billing-email");
    if (emailInput && !emailInput.value) {
      emailInput.value = getUserEmail();
    }
    
    renderCheckoutSummary();
  } else {
    // Not logged in - show auth choice
    if (authChoice) authChoice.style.display = "block";
    if (checkoutContent) checkoutContent.style.display = "none";
  }
}

function continueAsGuest() {
  const authChoice = document.getElementById("checkout-auth-choice");
  const checkoutContent = document.getElementById("checkout-content");
  
  if (authChoice) authChoice.style.display = "none";
  if (checkoutContent) checkoutContent.style.display = "block";
  
  renderCheckoutSummary();
}

function closeCheckoutModal() {
  const modal = document.getElementById("checkout-modal");
  const authChoice = document.getElementById("checkout-auth-choice");
  const checkoutContent = document.getElementById("checkout-content");
  const paymentInstructions = document.getElementById("payment-instructions");
  
  if (modal) modal.style.display = "none";
  
  // Reset state for next checkout
  if (authChoice) authChoice.style.display = "none";
  if (checkoutContent) checkoutContent.style.display = "block";
  if (paymentInstructions) {
    paymentInstructions.style.display = "none";
    paymentInstructions.innerHTML = "";
  }

  // Reset currency to AOA
  selectedCurrency = "AOA";
  const aoaRadio = document.querySelector('input[name="checkout-currency"][value="AOA"]');
  if (aoaRadio) aoaRadio.checked = true;
  onCurrencyChange("AOA");
}

function renderCheckoutSummary() {
  const summary = document.getElementById("checkout-summary");
  if (!summary || !currentCart) return;

  let html = "<ul>";
  currentCart.items.forEach((item) => {
    const product = allProducts.find(p => p.id === item.product_id);
    const itemName = product ? localizedProductCopy(product).name : item.product_name;
    html += `<li>${item.quantity}x ${esc(itemName)} - ${formatAOA(item.total_price)}</li>`;
  });
  html += "</ul>";
  
  if (currentCart.discount_amount > 0) {
    html += `<p><strong>Desconto:</strong> -${formatAOA(currentCart.discount_amount)}</p>`;
  }
  html += `<p style="font-size:0.85rem;color:#94a3b8;"><em>${esc(storeT('loja.checkout.taxIncluded'))}: ${formatAOA(currentCart.tax_amount)}</em></p>`;
  html += `<p class="checkout-total"><strong>Total:</strong> ${formatAOA(currentCart.total)}</p>`;

  // Multi-currency totals
  const totals = computeMultiCurrencyTotals();
  html += `<div class="checkout-multi-totals" style="margin-top:0.8rem;padding-top:0.8rem;border-top:1px solid rgba(148,163,184,0.2);">
    <p style="font-size:0.75rem;color:#94a3b8;margin-bottom:0.4rem;text-transform:uppercase;letter-spacing:0.1em;">${esc(storeT('loja.checkout.allCurrencies'))}:</p>
    <div style="display:flex;flex-direction:column;gap:0.3rem;">
      <div style="display:flex;justify-content:space-between;align-items:center;"><span class="cur-badge cur-aoa" style="font-size:0.7rem;">AOA</span><strong>${formatPrice(totals.aoa, 'AOA')}</strong></div>
      <div style="display:flex;justify-content:space-between;align-items:center;"><span class="cur-badge cur-usd" style="font-size:0.7rem;">USD</span><strong>${formatPrice(totals.usd, 'USD')}</strong></div>
      <div style="display:flex;justify-content:space-between;align-items:center;"><span class="cur-badge cur-eur" style="font-size:0.7rem;">EUR</span><strong>${formatPrice(totals.eur, 'EUR')}</strong></div>
    </div>
  </div>`;
  
  summary.innerHTML = html;
}

async function processCheckout() {
  const name = document.getElementById("billing-name")?.value?.trim();
  const email = document.getElementById("billing-email")?.value?.trim();
  const phone = document.getElementById("billing-phone")?.value?.trim();
  const company = document.getElementById("billing-company")?.value?.trim();
  const nif = document.getElementById("billing-nif")?.value?.trim();
  const paymentMethod = document.querySelector('input[name="payment"]:checked')?.value;

  if (!email || !name) {
    alert("Please fill in name and email.");
    return;
  }

  if (!paymentMethod) {
    alert("Please select a payment method.");
    return;
  }

  // Loading state
  const btn = document.getElementById("confirm-checkout-btn");
  const btnOrigText = btn ? btn.textContent : "";
  if (btn) { btn.disabled = true; btn.textContent = storeT("loja.checkout.processing"); btn.style.opacity = "0.7"; }

  try {
    const token = localStorage.getItem("gv_token");
    const headers = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const res = await fetch(`${API_URL}/shop/checkout/${cartId}`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        payment_method: paymentMethod,
        currency: selectedCurrency || "AOA",
        billing_info: {
          name,
          email,
          phone: phone || null,
          company: company || null,
          nif: nif || null,
          country: "",
        },
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Erro no checkout (${res.status})`);
    }

    const result = await res.json();

    // Mostrar resultado baseado no método de pagamento
    showPaymentInstructions(result);
    
    // Limpar carrinho local
    currentCart = { items: [], total: 0, item_count: 0 };
    renderCart();
    
    // Gerar novo cart ID para próxima compra
    cartId = generateCartId();

  } catch (err) {
    console.error("Erro no checkout:", err);
    alert(err.message);
    // Restore button
    if (btn) { btn.disabled = false; btn.textContent = btnOrigText; btn.style.opacity = "1"; }
  }
}

function showPaymentInstructions(result) {
  const checkoutContent = document.getElementById("checkout-content");
  const paymentInstructions = document.getElementById("payment-instructions");
  
  if (!paymentInstructions) {
    alert(storeFormat("loja.checkout.orderCreatedRef", { number: result.order_number }));
    return;
  }

  // Hide checkout form, show payment instructions
  if (checkoutContent) checkoutContent.style.display = "none";
  paymentInstructions.style.display = "block";

  let html = `
    <div class="payment-instructions" style="text-align:center;">
      <p class="order-success" style="font-size:1.3rem;margin-bottom:0.5rem;">✓ ${esc(storeT('loja.checkout.orderCreated'))}</p>
      <p style="font-size:1.1rem;font-weight:600;margin-bottom:1rem;">${esc(result.order_number)}</p>
  `;

  const pd = result.payment_data || {};

  if (result.payment_method === "multicaixa_express" && pd.qr_code) {
    html += `
      <div class="payment-instructions">
        <h3>Multicaixa Express</h3>
        <p>${esc(storeT('loja.payment.scanQr'))}</p>
        <div class="qr-container">
          <img src="https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(pd.qr_code)}" alt="QR Code" />
        </div>
        <p class="ref-code">Ref: ${esc(pd.provider_reference || "")}</p>
      </div>
    `;
  } else if (result.payment_method === "visa_mastercard" && pd.client_secret) {
    html += `
      <div class="payment-instructions">
        <h3><i class="fa-brands fa-cc-stripe" style="color:#635bff;"></i> ${esc(storeT('loja.payment.cardTitle'))}</h3>
        <p>${esc(storeT('loja.payment.cardDetails'))}</p>
        <div id="stripe-payment-element" style="min-height:120px;margin:1rem 0;padding:1rem;border:1px solid rgba(255,255,255,0.1);border-radius:8px;background:rgba(0,0,0,0.2);"></div>
        <div id="stripe-error" style="color:#f97373;font-size:0.85rem;min-height:1.2rem;margin-bottom:0.5rem;"></div>
        <button id="stripe-pay-btn" class="checkout-btn" style="width:100%;margin-top:0.5rem;" onclick="confirmStripePayment()">
          ${esc(storeT('loja.payment.payNow'))}
        </button>
        <p style="font-size:.75rem;color:#94a3b8;margin-top:.5rem;">${esc(storeT('loja.payment.stripeSecure'))}</p>
      </div>
    `;
    // Mount Stripe Elements after inserting HTML
    setTimeout(() => mountStripePaymentElement(pd.client_secret), 50);
  } else if (result.payment_method === "visa_mastercard") {
    // Stripe not configured or client_secret missing — show fallback
    html += `
      <div class="payment-instructions">
        <h3>${esc(storeT('loja.payment.cardTitle'))}</h3>
        <p>${esc(storeT('loja.payment.cardUnavailable'))}</p>
        <p style="font-size:.85rem;color:#94a3b8;margin-top:.5rem;">${esc(storeT('loja.payment.cardAlternative'))}</p>
      </div>
    `;
  } else if (result.payment_method === "iban_angola" && pd.transfer_details) {
    const td = pd.transfer_details;
    html += `
      <div class="payment-instructions">
        <h3>${esc(storeT('loja.payment.bankTransfer'))}</h3>
        <p>${esc(storeT('loja.payment.bankInstructions'))}</p>
        <div class="bank-details">
          <p><strong>${esc(storeT('loja.payment.bank'))}:</strong> ${esc(td.bank_name)}</p>
          <p><strong>IBAN:</strong> ${esc(td.iban)}</p>
          <p><strong>${esc(storeT('loja.payment.beneficiary'))}:</strong> ${esc(td.beneficiary || "GeoVision Lda")}</p>
          <p><strong>${esc(storeT('loja.payment.reference'))}:</strong> ${esc(td.reference || result.order_number)}</p>
          <p><strong>${esc(storeT('loja.payment.amount'))}:</strong> ${td.amount?.toLocaleString("pt-AO")} AOA</p>
        </div>
      </div>
    `;
  } else if (result.payment_method === "iban_international" && pd.transfer_details) {
    const td = pd.transfer_details;
    const cur = td.currency || "EUR";
    html += `
      <div class="payment-instructions">
        <h3>${esc(storeT('loja.payment.internationalTransfer'))}</h3>
        <div class="bank-details">
          <p><strong>${esc(storeT('loja.payment.bank'))}:</strong> ${esc(td.bank_name)}</p>
          <p><strong>IBAN:</strong> ${esc(td.iban)}</p>
          <p><strong>SWIFT/BIC:</strong> ${esc(td.bic)}</p>
          <p><strong>${esc(storeT('loja.payment.beneficiary'))}:</strong> ${esc(td.beneficiary || "GeoVision Lda")}</p>
          <p><strong>${esc(storeT('loja.payment.reference'))}:</strong> ${esc(td.reference || result.order_number)}</p>
          <p><strong>${esc(storeT('loja.payment.amount'))}:</strong> ${td.amount?.toLocaleString("pt-PT", {minimumFractionDigits: 2})} ${cur}</p>
        </div>
      </div>
    `;
  } else if (result.payment_method === "paypal" && pd.redirect_url) {
    // Validate PayPal redirect URL - must be https
    const paypalUrl = /^https:\/\//.test(pd.redirect_url) ? pd.redirect_url : '#';
    html += `
      <div class="payment-instructions">
        <h3><i class="fa-brands fa-paypal" style="color:#003087;"></i> ${esc(storeT('loja.payment.paypalTitle'))}</h3>
        <p>${esc(storeT('loja.payment.paypalBody'))}</p>
        <a href="${esc(paypalUrl)}" class="btn-payment" target="_blank"
           style="display:inline-flex;align-items:center;gap:.5rem;background:#0070ba;color:#fff;padding:.8rem 2rem;border-radius:8px;text-decoration:none;font-weight:600;margin:1rem 0;">
          <i class="fa-brands fa-paypal"></i> ${esc(storeT('loja.payment.paypalTitle'))}
        </a>
        <p style="font-size:.75rem;color:#94a3b8;margin-top:.5rem;">Ref: ${esc(pd.provider_reference || "")}</p></p>
      </div>
    `;
  } else {
    html += `
      <div class="payment-instructions">
        <p>${esc(storeT('loja.payment.awaiting'))}</p>
      </div>
    `;
  }

  html += `
      <button class="checkout-btn" onclick="closeCheckoutModal()">${esc(storeT('loja.payment.close'))}</button>
    </div>
  `;

  paymentInstructions.innerHTML = html;
}

// ============ STRIPE PAYMENT ELEMENT ============

async function initStripe() {
  if (stripeInstance) return;
  try {
    const res = await fetch(`${API_URL}/shop/stripe-config`);
    if (!res.ok) return;
    const cfg = await res.json();
    if (cfg.enabled && cfg.publishable_key && typeof Stripe !== "undefined") {
      stripeInstance = Stripe(cfg.publishable_key);
    }
  } catch (e) {
    console.warn("Stripe init skipped:", e.message);
  }
}

function mountStripePaymentElement(clientSecret) {
  if (!stripeInstance) {
    const errEl = document.getElementById("stripe-error");
    if (errEl) errEl.textContent = storeT("loja.payment.stripeMissing");
    return;
  }
  const appearance = {
    theme: "night",
    variables: { colorPrimary: "#38bdf8", colorBackground: "#0f172a", colorText: "#e2e8f0", fontFamily: "system-ui, sans-serif", borderRadius: "8px" },
  };
  stripeElements = stripeInstance.elements({ clientSecret, appearance });
  const paymentEl = stripeElements.create("payment");
  paymentEl.mount("#stripe-payment-element");
}

async function confirmStripePayment() {
  if (!stripeInstance || !stripeElements) return;
  const btn = document.getElementById("stripe-pay-btn");
  const errEl = document.getElementById("stripe-error");
  if (btn) { btn.disabled = true; btn.textContent = "A processar..."; }
  if (errEl) errEl.textContent = "";

  const { error } = await stripeInstance.confirmPayment({
    elements: stripeElements,
    confirmParams: {
      return_url: window.location.origin + "/loja.html?payment=success",
    },
  });

  // If we get here, there was an error (otherwise user is redirected)
  if (error) {
    if (errEl) errEl.textContent = error.message;
    if (btn) { btn.disabled = false; btn.textContent = "Pagar Agora"; }
  }
}
window.confirmStripePayment = confirmStripePayment;



// ============ TOAST ============

function showToast(message) {
  let toast = document.getElementById("toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "toast";
    toast.style.cssText = `
      position: fixed;
      bottom: 20px;
      left: 50%;
      transform: translateX(-50%);
      background: linear-gradient(135deg, #22c55e, #38bdf8);
      color: #020617;
      padding: 12px 24px;
      border-radius: 999px;
      font-weight: 500;
      z-index: 9999;
      opacity: 0;
      transition: opacity 0.3s;
    `;
    document.body.appendChild(toast);
  }

  toast.textContent = message;
  toast.style.opacity = "1";

  setTimeout(() => {
    toast.style.opacity = "0";
  }, 2000);
}

// ============ EXPOR FUNÇÕES GLOBAIS ============

window.addToCart = addToCart;
window.handleAddToCart = handleAddToCart;
window.removeFromCart = removeFromCart;
window.updateCartQty = updateCartQty;
window.clearCart = clearCart;
window.applyCoupon = applyCoupon;
window.openCheckoutModal = openCheckoutModal;
window.closeCheckoutModal = closeCheckoutModal;
window.processCheckout = processCheckout;
window.selectPayment = selectPayment;
window.closeSectorWarning = closeSectorWarning;
window.continueAddToCart = continueAddToCart;
window.redirectToCreateAccount = redirectToCreateAccount;
window.onCurrencyChange = onCurrencyChange;
window.continueAsGuest = continueAsGuest;

// ============ SELECT PAYMENT ============

function selectPayment(method) {
  const options = document.querySelectorAll(".payment-option");
  options.forEach(opt => {
    const radio = opt.querySelector('input[type="radio"]');
    if (radio && radio.value === method) {
      opt.classList.add("selected");
      radio.checked = true;
    } else {
      opt.classList.remove("selected");
    }
  });
}

// ============ INIT ============

document.addEventListener("DOMContentLoaded", () => {
  if (!document.body || document.body.getAttribute("data-page") !== "loja") {
    return;
  }

  setupFilters();
  loadProducts();
  loadCart();
  loadPaymentMethods();
  initStripe();

  // Handle Stripe return redirect
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get("payment") === "success" || urlParams.get("redirect_status") === "succeeded") {
    showToast("Pagamento processado com sucesso! ✓");
    // Clean URL
    window.history.replaceState({}, "", window.location.pathname);
  }

  const btnClear = document.getElementById("cart-clear");
  const btnCheckout = document.getElementById("cart-checkout");
  const btnCoupon = document.getElementById("apply-coupon");

  if (btnClear) btnClear.addEventListener("click", clearCart);
  if (btnCheckout) btnCheckout.addEventListener("click", openCheckoutModal);
  if (btnCoupon) btnCoupon.addEventListener("click", applyCoupon);
});
