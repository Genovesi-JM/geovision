/**
 * GeoVision Shop (loja.js)
 * 
 * Integração completa com backend /shop API:
 *  - Catálogo de produtos (/shop/products)
 *  - Carrinho (/shop/cart)
 *  - Checkout com 4 métodos de pagamento
 *  - Tracking de pedidos
 */

const API_URL = window.API_BASE || "http://127.0.0.1:8010";

// Estado da loja
let allProducts = [];
let cartId = localStorage.getItem("gv_cart_id") || generateCartId();
let currentCart = null;
let currentSectorFilter = "all";
let currentTypeFilter = "all";
let pendingAddProduct = null;
let stripeInstance = null;
let stripeElements = null;

// Sector labels for display
const SECTOR_LABELS = {
  "mining": "Mineração",
  "infrastructure": "Construção e Infraestrutura",
  "agro": "Agro & Pecuária",
  "demining": "Desminagem Humanitária",
  "solar": "Solar & Energia",
  "livestock": "Pecuária",
};

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

async function onCurrencyChange(currency) {
  selectedCurrency = currency;
  // Show/hide payment methods based on currency
  document.querySelectorAll('.payment-option[data-currencies]').forEach(el => {
    const currencies = el.getAttribute('data-currencies').split(',');
    if (currencies.includes(currency)) {
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
      empty.textContent = "Não foi possível carregar os produtos. Verifique a conexão e tente novamente.";
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
    empty.textContent = "O carrinho está vazio.";
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
    const row = document.createElement("div");
    row.className = "loja-cart-item";
    row.innerHTML = `
      <div>
        <div class="loja-cart-item-name">${item.product_name}</div>
        <div class="loja-cart-item-meta">
          ${item.quantity} × ${formatAOASimple(item.unit_price)}
        </div>
      </div>
      <div class="loja-cart-item-actions">
        <div class="qty-stepper">
          <button class="qty-minus" onclick="updateCartQty('${item.id}', ${item.quantity - 1})" title="Remover 1">−</button>
          <span class="qty-val">${item.quantity}</span>
          <button class="qty-plus" onclick="updateCartQty('${item.id}', ${item.quantity + 1})" title="Adicionar 1">+</button>
        </div>
        <button class="cart-remove-btn" onclick="removeFromCart('${item.id}')" title="Remover">
          ✕
        </button>
      </div>
    `;
    list.appendChild(row);
  });

  const countLabel = currentCart.item_count === 1 ? "1 item" : `${currentCart.item_count} items`;
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
        couponStatus.textContent = `Cupão "${currentCart.coupon_code}" aplicado!`;
        couponStatus.style.display = "block";
      }
    } else {
      discountRow.style.display = "none";
      if (couponStatus) couponStatus.style.display = "none";
    }
  }
  
  // Update tax
  if (taxRow && taxEl) {
    if (currentCart.tax_amount > 0) {
      taxRow.style.display = "flex";
      taxEl.textContent = formatAOA(currentCart.tax_amount);
    } else {
      taxRow.style.display = "none";
    }
  }
  
  // Update main total
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
  const taxRate = 0.14;

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

  // Apply tax
  totals.aoa = Math.round(totals.aoa * (1 + taxRate));
  totals.usd = Math.round(totals.usd * (1 + taxRate));
  totals.eur = Math.round(totals.eur * (1 + taxRate));

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
  
  const productSectorLabels = data.product_sectors.map(s => SECTOR_LABELS[s] || s).join(", ");
  const userSectorLabel = SECTOR_LABELS[data.user_sector] || data.user_sector || "não definido";
  
  msgEl.innerHTML = `
    <p><strong>Atenção:</strong> Este produto pertence ao(s) setor(es) <strong>${productSectorLabels}</strong>, 
    mas a sua conta está registada no setor <strong>${userSectorLabel}</strong>.</p>
    <p>Deseja continuar assim mesmo?</p>
  `;
  
  modal.style.display = "flex";
}

function closeSectorWarning() {
  const modal = document.getElementById("sector-warning-modal");
  if (modal) modal.style.display = "none";
  pendingAddProduct = null;
}

async function continueAddToCart() {
  closeSectorWarning();
  if (pendingAddProduct) {
    await addToCart(pendingAddProduct);
    pendingAddProduct = null;
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
    "analysis": "Análise",
    "mapping": "Mapeamento",
    "spraying": "Pulverização",
    "monitoring": "Monitorização",
    "flight": "Voo",
  };
  return mapping[category] || category || "Serviço";
}

function mapFilterKey(product) {
  const type = product.product_type;
  if (type === "service") return "servico";
  if (type === "subscription") return "subscription";
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

  let filtered = allProducts;
  
  // Apply sector filter
  if (currentSectorFilter !== "all") {
    filtered = filtered.filter((p) => 
      (p.sectors || []).includes(currentSectorFilter)
    );
  }
  
  // Apply type filter
  if (currentTypeFilter !== "all") {
    filtered = filtered.filter((p) => mapFilterKey(p) === currentTypeFilter);
  }

  if (!filtered.length) {
    empty.style.display = "block";
    return;
  }
  empty.style.display = "none";

  // Sort: featured first, then by price
  filtered.sort((a, b) => {
    if (a.is_featured && !b.is_featured) return -1;
    if (!a.is_featured && b.is_featured) return 1;
    return 0;
  });

  filtered.forEach((p) => {
    const card = document.createElement("article");
    card.className = "loja-card";

    const catLabel = mapCategoryLabel(p.category);
    
    // Sector badges
    const sectorBadges = (p.sectors || []).map(s => 
      `<span class="${getSectorBadgeClass(s)}">${SECTOR_LABELS[s] || s}</span>`
    ).join("");

    // Execution type badge
    const execBadge = p.execution_type 
      ? `<span class="execution-badge ${p.execution_type}">${p.execution_type === 'pontual' ? 'Pontual' : 'Recorrente'}</span>`
      : '';

    // Meta info
    let metaHtml = '';
    if (p.duration_hours) {
      metaHtml += `<span>⏱️ ${p.duration_hours}h</span>`;
    }
    if (p.min_area_ha) {
      metaHtml += `<span><i class="fa-solid fa-ruler-combined"></i> Min ${p.min_area_ha}ha</span>`;
    }

    // Deliverables preview
    let deliverablesHtml = '';
    if (p.deliverables && p.deliverables.length > 0) {
      const preview = p.deliverables.slice(0, 3).join(", ");
      const more = p.deliverables.length > 3 ? ` +${p.deliverables.length - 3}` : '';
      deliverablesHtml = `<div class="deliverables-preview"><i class="fa-solid fa-box"></i> ${preview}${more}</div>`;
    }

    // Featured badge
    const featuredBadge = p.is_featured 
      ? '<span class="featured-badge">Destaque</span>' 
      : '';

    card.innerHTML = `
      ${featuredBadge}
      <div>
        <div class="loja-card-tag">${catLabel} ${execBadge}</div>
        <h3 class="loja-card-title">${p.name}</h3>
        <p class="loja-card-desc">
          ${p.short_description || p.description || "Serviço GeoVision integrado."}
        </p>
        <div class="loja-card-sectors">${sectorBadges}</div>
        ${metaHtml ? `<div class="loja-card-meta">${metaHtml}</div>` : ''}
        ${deliverablesHtml}
      </div>
      <div class="loja-card-footer">
        <div class="loja-prices-multi">
          <div class="loja-price-row loja-price-aoa${selectedCurrency === 'AOA' ? ' active' : ''}">
            <span class="cur-badge cur-aoa">AOA</span>
            ${formatPrice(p.price, 'AOA')}${p.unit_label ? `<span class="unit">/${p.unit_label}</span>` : ""}
          </div>
          <div class="loja-price-row loja-price-usd${selectedCurrency === 'USD' ? ' active' : ''}">
            <span class="cur-badge cur-usd">USD</span>
            ${formatPrice(p.price_usd || 0, 'USD')}${p.unit_label ? `<span class="unit">/${p.unit_label}</span>` : ""}
          </div>
          <div class="loja-price-row loja-price-eur${selectedCurrency === 'EUR' ? ' active' : ''}">
            <span class="cur-badge cur-eur">EUR</span>
            ${formatPrice(p.price_eur || 0, 'EUR')}${p.unit_label ? `<span class="unit">/${p.unit_label}</span>` : ""}
          </div>
        </div>
        <button class="btn-add" onclick="handleAddToCart('${p.id}')">
          Adicionar
        </button>
      </div>
    `;
    grid.appendChild(card);
  });
}

function setupFilters() {
  // Sector filter buttons (inside #sector-filters)
  const sectorButtons = document.querySelectorAll("#sector-filters .loja-filter-btn");
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
    alert("O carrinho está vazio.");
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
    html += `<li>${item.quantity}x ${item.product_name} - ${formatAOA(item.total_price)}</li>`;
  });
  html += "</ul>";
  
  if (currentCart.discount_amount > 0) {
    html += `<p><strong>Desconto:</strong> -${formatAOA(currentCart.discount_amount)}</p>`;
  }
  html += `<p><strong>IVA (14%):</strong> ${formatAOA(currentCart.tax_amount)}</p>`;
  html += `<p class="checkout-total"><strong>Total:</strong> ${formatAOA(currentCart.total)}</p>`;

  // Multi-currency totals
  const totals = computeMultiCurrencyTotals();
  html += `<div class="checkout-multi-totals" style="margin-top:0.8rem;padding-top:0.8rem;border-top:1px solid rgba(148,163,184,0.2);">
    <p style="font-size:0.75rem;color:#94a3b8;margin-bottom:0.4rem;text-transform:uppercase;letter-spacing:0.1em;">Valores em todas as moedas:</p>
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
      const err = await res.json();
      throw new Error(err.detail || "Erro no checkout");
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
  }
}

function showPaymentInstructions(result) {
  const checkoutContent = document.getElementById("checkout-content");
  const paymentInstructions = document.getElementById("payment-instructions");
  
  if (!paymentInstructions) {
    alert(`Pedido ${result.order_number} criado com sucesso!`);
    return;
  }

  // Hide checkout form, show payment instructions
  if (checkoutContent) checkoutContent.style.display = "none";
  paymentInstructions.style.display = "block";

  let html = `
    <div class="payment-instructions" style="text-align:center;">
      <p class="order-success" style="font-size:1.3rem;margin-bottom:0.5rem;">✓ Pedido Criado</p>
      <p style="font-size:1.1rem;font-weight:600;margin-bottom:1rem;">${result.order_number}</p>
  `;

  const pd = result.payment_data || {};

  if (result.payment_method === "multicaixa_express" && pd.qr_code) {
    html += `
      <div class="payment-instructions">
        <h3>Multicaixa Express</h3>
        <p>Scan the QR code with the Multicaixa Express app:</p>
        <div class="qr-container">
          <img src="https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(pd.qr_code)}" alt="QR Code" />
        </div>
        <p class="ref-code">Ref: ${pd.provider_reference || ""}</p>
      </div>
    `;
  } else if (result.payment_method === "visa_mastercard" && pd.client_secret) {
    html += `
      <div class="payment-instructions">
        <h3><i class="fa-brands fa-cc-stripe" style="color:#635bff;"></i> Pagar com Cartão</h3>
        <p>Introduz os dados do cartão abaixo:</p>
        <div id="stripe-payment-element" style="min-height:120px;margin:1rem 0;padding:1rem;border:1px solid rgba(255,255,255,0.1);border-radius:8px;background:rgba(0,0,0,0.2);"></div>
        <div id="stripe-error" style="color:#f97373;font-size:0.85rem;min-height:1.2rem;margin-bottom:0.5rem;"></div>
        <button id="stripe-pay-btn" class="checkout-btn" style="width:100%;margin-top:0.5rem;" onclick="confirmStripePayment()">
          Pagar Agora
        </button>
        <p style="font-size:.75rem;color:#94a3b8;margin-top:.5rem;">Pagamento seguro via Stripe</p>
      </div>
    `;
    // Mount Stripe Elements after inserting HTML
    setTimeout(() => mountStripePaymentElement(pd.client_secret), 50);
  } else if (result.payment_method === "visa_mastercard") {
    // Stripe not configured or client_secret missing — show fallback
    html += `
      <div class="payment-instructions">
        <h3>Pagar com Cartão</h3>
        <p>O pagamento por cartão está temporariamente indisponível. Tenta outro método.</p>
      </div>
    `;
  } else if (result.payment_method === "iban_angola" && pd.transfer_details) {
    const td = pd.transfer_details;
    html += `
      <div class="payment-instructions">
        <h3>Bank Transfer</h3>
        <p>Transfer to the account below and send proof of payment:</p>
        <div class="bank-details">
          <p><strong>Banco:</strong> ${td.bank_name}</p>
          <p><strong>IBAN:</strong> ${td.iban}</p>
          <p><strong>Beneficiário:</strong> ${td.beneficiary || "GeoVision Lda"}</p>
          <p><strong>Referência:</strong> ${td.reference || result.order_number}</p>
          <p><strong>Valor:</strong> ${td.amount?.toLocaleString("pt-AO")} AOA</p>
        </div>
      </div>
    `;
  } else if (result.payment_method === "iban_international" && pd.transfer_details) {
    const td = pd.transfer_details;
    const cur = td.currency || "EUR";
    html += `
      <div class="payment-instructions">
        <h3>Transferência Internacional (SWIFT/SEPA)</h3>
        <div class="bank-details">
          <p><strong>Banco:</strong> ${td.bank_name}</p>
          <p><strong>IBAN:</strong> ${td.iban}</p>
          <p><strong>SWIFT/BIC:</strong> ${td.bic}</p>
          <p><strong>Beneficiário:</strong> ${td.beneficiary || "GeoVision Lda"}</p>
          <p><strong>Referência:</strong> ${td.reference || result.order_number}</p>
          <p><strong>Valor:</strong> ${td.amount?.toLocaleString("pt-PT", {minimumFractionDigits: 2})} ${cur}</p>
        </div>
      </div>
    `;
  } else if (result.payment_method === "paypal" && pd.redirect_url) {
    html += `
      <div class="payment-instructions">
        <h3><i class="fa-brands fa-paypal" style="color:#003087;"></i> Pagar com PayPal</h3>
        <p>Serás redirecionado para o PayPal para completar o pagamento.</p>
        <a href="${pd.redirect_url}" class="btn-payment" target="_blank"
           style="display:inline-flex;align-items:center;gap:.5rem;background:#0070ba;color:#fff;padding:.8rem 2rem;border-radius:8px;text-decoration:none;font-weight:600;margin:1rem 0;">
          <i class="fa-brands fa-paypal"></i> Pagar com PayPal
        </a>
        <p style="font-size:.75rem;color:#94a3b8;margin-top:.5rem;">Ref: ${pd.provider_reference || ""}</p>
      </div>
    `;
  } else {
    html += `
      <div class="payment-instructions">
        <p>Aguarda confirmação. Entraremos em contacto em breve.</p>
      </div>
    `;
  }

  html += `
      <button class="checkout-btn" onclick="closeCheckoutModal()">Fechar</button>
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
    if (errEl) errEl.textContent = "Stripe não está configurado. Contacta o suporte.";
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

  loadProducts();
  loadCart();
  setupFilters();
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
