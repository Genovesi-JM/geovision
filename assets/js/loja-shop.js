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

// Guardar cartId no localStorage
function generateCartId() {
  const id = "cart_" + Math.random().toString(36).substring(2, 15);
  localStorage.setItem("gv_cart_id", id);
  return id;
}

// ============ FORMATAÇÃO ============

function formatAOA(cents) {
  const value = cents / 100;
  return value.toLocaleString("pt-AO", {
    style: "currency",
    currency: "AOA",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
}

function formatAOASimple(cents) {
  const value = cents / 100;
  return value.toLocaleString("pt-AO") + " AOA";
}

// ============ CARREGAR PRODUTOS ============

async function loadProducts() {
  try {
    const res = await fetch(`${API_URL}/shop/products`);
    if (!res.ok) throw new Error("Falha ao carregar produtos");
    
    allProducts = await res.json();
    renderProducts("all");
  } catch (err) {
    console.error("Erro ao carregar produtos:", err);
    const empty = document.getElementById("loja-empty");
    if (empty) {
      empty.style.display = "block";
      empty.textContent = "Não foi possível carregar os produtos. Backend offline?";
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
    if (couponStatus) couponStatus.style.display = "none";
    return;
  }

  currentCart.items.forEach((item) => {
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
        <button style="border:none;background:none;color:#f97373;font-size:0.75rem;cursor:pointer;"
          onclick="removeFromCart('${item.id}')">
          ✕
        </button>
      </div>
    `;
    list.appendChild(row);
  });

  const countLabel = currentCart.item_count === 1 ? "1 item" : `${currentCart.item_count} itens`;
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
  
  // Update total
  totalEl.textContent = formatAOA(currentCart.total);
}

// ============ ADICIONAR AO CARRINHO ============

async function addToCart(productId) {
  try {
    const res = await fetch(`${API_URL}/shop/cart/${cartId}/items`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        product_id: productId,
        quantity: 1,
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
    "hardware": "Hardware & IoT",
    "supplies": "Insumos",
  };
  return mapping[category] || category || "Serviço";
}

function mapFilterKey(product) {
  const type = product.product_type;
  if (type === "service") return "servico";
  if (type === "subscription") return "servico";
  if (type === "physical" && product.category === "hardware") return "hardware";
  if (type === "physical" && product.category === "supplies") return "insumo";
  return "servico";
}

function renderProducts(filterKey = "all") {
  const grid = document.getElementById("loja-grid");
  const empty = document.getElementById("loja-empty");

  if (!grid || !empty) return;

  grid.innerHTML = "";

  let filtered = allProducts;
  if (filterKey !== "all") {
    filtered = allProducts.filter((p) => mapFilterKey(p) === filterKey);
  }

  if (!filtered.length) {
    empty.style.display = "block";
    return;
  }
  empty.style.display = "none";

  filtered.forEach((p) => {
    const card = document.createElement("article");
    card.className = "loja-card";

    const catLabel = mapCategoryLabel(p.category);
    const sectorBadges = (p.sectors || []).map(s => 
      `<span class="sector-badge">${s}</span>`
    ).join(" ");

    card.innerHTML = `
      <div>
        <div class="loja-card-tag">${catLabel}</div>
        <h3 class="loja-card-title">${p.name}</h3>
        <p class="loja-card-desc">
          ${p.description || "Serviço GeoVision integrado."}
        </p>
        <div class="loja-card-sectors">${sectorBadges}</div>
      </div>
      <div class="loja-card-footer">
        <div class="loja-price">
          ${formatAOA(p.price)}
          ${p.unit_label ? `<span>/${p.unit_label}</span>` : ""}
        </div>
        <button class="btn-add" onclick="addToCart('${p.id}')">
          Adicionar
        </button>
      </div>
    `;
    grid.appendChild(card);
  });
}

function setupFilters() {
  const buttons = document.querySelectorAll(".loja-filter-btn");
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const key = btn.getAttribute("data-filter");
      renderProducts(key);
    });
  });
}

// ============ CHECKOUT ============

async function openCheckoutModal() {
  if (!currentCart || !currentCart.items.length) {
    alert("O carrinho está vazio.");
    return;
  }

  const modal = document.getElementById("checkout-modal");
  if (modal) {
    modal.style.display = "flex";
    renderCheckoutSummary();
  }
}

function closeCheckoutModal() {
  const modal = document.getElementById("checkout-modal");
  const checkoutContent = document.getElementById("checkout-content");
  const paymentInstructions = document.getElementById("payment-instructions");
  
  if (modal) modal.style.display = "none";
  
  // Reset state for next checkout
  if (checkoutContent) checkoutContent.style.display = "block";
  if (paymentInstructions) {
    paymentInstructions.style.display = "none";
    paymentInstructions.innerHTML = "";
  }
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
    alert("Preenche o nome e email.");
    return;
  }

  if (!paymentMethod) {
    alert("Seleciona um método de pagamento.");
    return;
  }

  updateDemoPanel({ 
    payload: { payment_method: paymentMethod, billing_info: { name, email, phone } }, 
    status: "A processar checkout..." 
  });

  try {
    const res = await fetch(`${API_URL}/shop/checkout/${cartId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        payment_method: paymentMethod,
        billing_info: {
          name,
          email,
          phone: phone || null,
          company: company || null,
          nif: nif || null,
          country: "AO",
        },
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Erro no checkout");
    }

    const result = await res.json();
    
    updateDemoPanel({
      payload: { payment_method: paymentMethod },
      response: result,
      status: `Pedido ${result.order_number} criado!`,
    });

    // Mostrar resultado baseado no método de pagamento
    showPaymentInstructions(result);
    
    // Limpar carrinho local
    currentCart = { items: [], total: 0, item_count: 0 };
    renderCart();
    
    // Gerar novo cart ID para próxima compra
    cartId = generateCartId();

  } catch (err) {
    console.error("Erro no checkout:", err);
    updateDemoPanel({
      error: err,
      status: "Erro no checkout",
    });
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
        <h3>Pagar com Multicaixa Express</h3>
        <p>Escaneia o QR code com a app Multicaixa Express:</p>
        <div class="qr-container">
          <img src="https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(pd.qr_code)}" alt="QR Code" />
        </div>
        <p class="ref-code">Ref: ${pd.provider_reference || ""}</p>
      </div>
    `;
  } else if (result.payment_method === "visa_mastercard" && pd.redirect_url) {
    html += `
      <div class="payment-instructions">
        <h3>Pagar com Cartão</h3>
        <p>Serás redirecionado para a página de pagamento seguro.</p>
        <a href="${pd.redirect_url}" class="btn-payment" target="_blank">Pagar Agora</a>
      </div>
    `;
  } else if (result.payment_method === "iban_angola" && pd.transfer_details) {
    const td = pd.transfer_details;
    html += `
      <div class="payment-instructions">
        <h3>Transferência Bancária Angola</h3>
        <p>Transfere para a conta abaixo e envia o comprovativo:</p>
        <div class="bank-details">
          <p><strong>Banco:</strong> ${td.bank_name}</p>
          <p><strong>IBAN:</strong> ${td.iban}</p>
          <p><strong>Referência:</strong> ${result.order_number}</p>
          <p><strong>Valor:</strong> ${formatAOA(currentCart?.total || 0)}</p>
        </div>
      </div>
    `;
  } else if (result.payment_method === "iban_international" && pd.transfer_details) {
    const td = pd.transfer_details;
    html += `
      <div class="payment-instructions">
        <h3>Transferência Internacional (SWIFT)</h3>
        <div class="bank-details">
          <p><strong>Banco:</strong> ${td.bank_name}</p>
          <p><strong>IBAN:</strong> ${td.iban}</p>
          <p><strong>SWIFT/BIC:</strong> ${td.swift_bic}</p>
          <p><strong>Referência:</strong> ${result.order_number}</p>
        </div>
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

// ============ DEMO PANEL ============

function updateDemoPanel({ payload, response, error, status }) {
  const requestEl = document.getElementById("demo-request");
  const responseEl = document.getElementById("demo-response");
  const statusEl = document.getElementById("demo-status");

  if (!requestEl || !responseEl || !statusEl) return;

  requestEl.textContent = payload
    ? JSON.stringify(payload, null, 2)
    : "Sem dados de pedido ainda.";

  if (error) {
    responseEl.textContent = error.message || String(error);
    statusEl.textContent = status || "Erro";
    statusEl.style.color = "#f97373";
    return;
  }

  responseEl.textContent = response
    ? JSON.stringify(response, null, 2)
    : "Aguardando resposta.";

  statusEl.textContent = status || "Aguarda envio...";
  statusEl.style.color = "#38bdf8";
}

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
window.removeFromCart = removeFromCart;
window.clearCart = clearCart;
window.applyCoupon = applyCoupon;
window.openCheckoutModal = openCheckoutModal;
window.closeCheckoutModal = closeCheckoutModal;
window.processCheckout = processCheckout;
window.selectPayment = selectPayment;

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

  const btnClear = document.getElementById("cart-clear");
  const btnCheckout = document.getElementById("cart-checkout");
  const btnCoupon = document.getElementById("apply-coupon");

  if (btnClear) btnClear.addEventListener("click", clearCart);
  if (btnCheckout) btnCheckout.addEventListener("click", openCheckoutModal);
  if (btnCoupon) btnCoupon.addEventListener("click", applyCoupon);
});
