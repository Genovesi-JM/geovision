// assets/js/loja.js

const API_URL = window.API_BASE || "http://127.0.0.1:8010";

let allProducts = [];
let cart = [];

// ---------- UTIL CART ----------

function loadCart() {
  const raw = localStorage.getItem("cart");
  cart = raw ? JSON.parse(raw) : [];
}

function saveCart() {
  localStorage.setItem("cart", JSON.stringify(cart));
}

function getCartTotal() {
  return cart.reduce((sum, item) => sum + item.price * item.qty, 0);
}

// ---------- RENDER CART ----------

function renderCart() {
  const list = document.getElementById("cart-items");
  const countEl = document.getElementById("cart-count");
  const totalEl = document.getElementById("cart-total");

  if (!list || !countEl || !totalEl) {
    return;
  }

  list.innerHTML = "";

  if (!cart.length) {
    const empty = document.createElement("div");
    empty.className = "loja-empty";
    empty.textContent = "O carrinho está vazio.";
    list.appendChild(empty);
  } else {
    cart.forEach((item) => {
      const row = document.createElement("div");
      row.className = "loja-cart-item";
      row.innerHTML = `
        <div>
          <div class="loja-cart-item-name">${item.name}</div>
          <div class="loja-cart-item-meta">
            ${item.qty} × € ${item.price.toLocaleString("pt-PT", {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </div>
        </div>
        <div class="loja-cart-item-actions">
          <button style="border:none;background:none;color:#f97373;font-size:0.75rem;cursor:pointer;"
            onclick="removeFromCart(${item.id})">
            ✕
          </button>
        </div>
      `;
      list.appendChild(row);
    });
  }

  const countLabel = cart.length === 1 ? "1 item" : `${cart.length} itens`;
  countEl.textContent = countLabel;

  totalEl.textContent = `€ ${getCartTotal().toLocaleString("pt-PT", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function addToCart(id) {
  const product = allProducts.find((p) => p.id === id);
  if (!product) return;

  const existing = cart.find((i) => i.id === id);
  if (existing) {
    existing.qty += 1;
  } else {
    cart.push({
      id: product.id,
      name: product.name,
      price: Number(product.price_eur),
      qty: 1,
    });
  }
  saveCart();
  renderCart();
}

function removeFromCart(id) {
  cart = cart.filter((i) => i.id !== id);
  saveCart();
  renderCart();
}

function clearCart() {
  cart = [];
  saveCart();
  renderCart();
}

// Expor no window para usar com onclick
window.addToCart = addToCart;
window.removeFromCart = removeFromCart;
window.clearCart = clearCart;

// ---------- DEMO PANEL ----------

function updateDemoPanel({ payload, response, error, status }) {
  const requestEl = document.getElementById("demo-request");
  const responseEl = document.getElementById("demo-response");
  const statusEl = document.getElementById("demo-status");

  if (!requestEl || !responseEl || !statusEl) {
    return;
  }

  requestEl.textContent = payload
    ? JSON.stringify(payload, null, 2)
    : "Sem dados de pedido ainda.";

  if (error) {
    responseEl.textContent = error.message || String(error);
    statusEl.textContent = status || "Erro ao enviar";
    statusEl.style.color = "#f97373";
    return;
  }

  responseEl.textContent = response
    ? JSON.stringify(response, null, 2)
    : "Aguardando a resposta.";

  statusEl.textContent = status || "Aguarda envio...";
  statusEl.style.color = "#38bdf8";
}

// ---------- PRODUTOS / FILTROS ----------

function mapCategoryLabel(cat) {
  if (!cat) return "Outros";
  const c = cat.toLowerCase();

  if (c.includes("servico") || c.includes("drone")) return "Serviço de campo";
  if (c.includes("hardware") || c.includes("sensor") || c.includes("iot")) return "Hardware & IoT";
  if (c.includes("insumo") || c.includes("semente") || c.includes("fertilizante") || c.includes("ração")) {
    return "Insumo & nutrição";
  }
  if (c.includes("pacote") || c.includes("pack")) return "Pacote GeoVision";

  return cat;
}

function mapFilterKey(cat) {
  if (!cat) return "outros";
  const c = cat.toLowerCase();
  if (c.includes("servico")) return "servico";
  if (c.includes("hardware") || c.includes("sensor") || c.includes("iot")) return "hardware";
  if (c.includes("insumo") || c.includes("semente") || c.includes("fertilizante") || c.includes("ração")) {
    return "insumo";
  }
  if (c.includes("pacote") || c.includes("pack")) return "pacote";
  return "outros";
}

function renderProducts(filterKey = "all") {
  const grid = document.getElementById("loja-grid");
  const empty = document.getElementById("loja-empty");

  if (!grid || !empty) return;

  grid.innerHTML = "";

  let filtered = allProducts;
  if (filterKey !== "all") {
    filtered = allProducts.filter((p) => mapFilterKey(p.category) === filterKey);
  }

  if (!filtered.length) {
    empty.style.display = "block";
    return;
  } else {
    empty.style.display = "none";
  }

  filtered.forEach((p) => {
    const card = document.createElement("article");
    card.className = "loja-card";

    const catLabel = mapCategoryLabel(p.category);
    const unitText = p.unit_label ? `/${p.unit_label}` : "";

    card.innerHTML = `
      <div>
        <div class="loja-card-tag">${catLabel}</div>
        <h3 class="loja-card-title">${p.name}</h3>
        <p class="loja-card-desc">
          ${p.description || "Serviço ou produto ligado à inteligência de campo GeoVision."}
        </p>
      </div>
      <div class="loja-card-footer">
        <div class="loja-price">
          € ${p.price_eur.toLocaleString("pt-PT", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
          })}
          <span>${unitText}</span>
        </div>
        <button class="btn-add" onclick="addToCart(${p.id})">
          Adicionar ao pedido
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

// ---------- CHECKOUT DEMO (PASSO 5) ----------

async function checkoutDemo() {
  if (!cart.length) {
    alert("O carrinho está vazio.");
    return;
  }

  const name = (document.getElementById("checkout-name")?.value || "").trim();
  const company = (document.getElementById("checkout-company")?.value || "").trim();
  const email = (document.getElementById("checkout-email")?.value || "").trim();
  const phone = (document.getElementById("checkout-phone")?.value || "").trim();
  const notes = (document.getElementById("checkout-notes")?.value || "").trim();

  if (!email) {
    alert("Indica um email para enviar o pedido.");
    return;
  }

  const payload = {
    customer_email: email,
    customer_name: name || null,
    customer_company: company || null,
    customer_phone: phone || null,
    notes: notes || null,
    items: cart.map((item) => ({
      product_id: item.id,
      quantity: item.qty,
    })),
  };

  updateDemoPanel({ payload, status: "A enviar..." });

  try {
    const res = await fetch(`${API_URL}/orders/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      const detail = errorData.detail || "Não foi possível enviar o pedido.";
      throw new Error(detail);
    }

    const order = await res.json();

    clearCart();
    updateDemoPanel({
      payload,
      response: order,
      status: `Pedido criado (#${order.id})`,
    });
    alert(`Pedido #${order.id} registado. A equipa GeoVision entrará em contacto.`);
  } catch (err) {
    console.error(err);
    updateDemoPanel({
      payload,
      error: err,
      status: "Erro no envio",
    });
    alert(err.message || "Não foi possível finalizar o pedido. Verifica o backend.");
  }
}

window.checkoutDemo = checkoutDemo;

// ---------- INIT ----------

async function loadProductsFromAPI() {
  try {
    const res = await fetch(`${API_URL}/products/`);
    if (!res.ok) {
      throw new Error("Falha ao carregar produtos");
    }
    const data = await res.json();
    allProducts = (data || []).map((p) => ({
      ...p,
      price_eur: Number(p.price_cents || 0) / 100,
    }));
    renderProducts("all");
  } catch (err) {
    console.error(err);
    document.getElementById("loja-empty").style.display = "block";
    document.getElementById("loja-empty").textContent =
      "Não foi possível carregar os produtos. Verifica se o backend está ligado.";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  if (!document.body || document.body.getAttribute("data-page") !== "loja") {
    return;
  }

  loadCart();
  renderCart();
  setupFilters();
  loadProductsFromAPI();

  const btnClear = document.getElementById("cart-clear");
  const btnCheckout = document.getElementById("cart-checkout");

  if (btnClear) btnClear.addEventListener("click", clearCart);
  if (btnCheckout) btnCheckout.addEventListener("click", checkoutDemo);
});
