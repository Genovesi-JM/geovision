// loja-cart.js
// Gestão de carrinho da Loja GeoVision (demo)
// - localStorage
// - adicionar item
// - remover item
// - limpar tudo

const GV_CART_KEY = "geovision_cart";

/* ---------- HELPERS LOCALSTORAGE ---------- */

function gvLoadCart() {
  try {
    const raw = localStorage.getItem(GV_CART_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed;
  } catch (e) {
    console.warn("Erro a ler carrinho:", e);
    return [];
  }
}

function gvSaveCart(cart) {
  try {
    localStorage.setItem(GV_CART_KEY, JSON.stringify(cart));
  } catch (e) {
    console.warn("Erro a guardar carrinho:", e);
  }
}

/* ---------- LÓGICA DO CARRINHO ---------- */

function gvAddToCart(productId, name, price) {
  const cart = gvLoadCart();
  const existing = cart.find((item) => item.id === productId);

  if (existing) {
    existing.qty += 1;
  } else {
    cart.push({
      id: productId,
      name,
      price: Number(price) || 0,
      qty: 1,
    });
  }

  gvSaveCart(cart);
  gvRenderCart();
}

function gvRemoveFromCart(productId) {
  let cart = gvLoadCart();
  cart = cart.filter((item) => item.id !== productId);
  gvSaveCart(cart);
  gvRenderCart();
}

function gvClearCart() {
  gvSaveCart([]);
  gvRenderCart();
}

/* ---------- RENDERIZAÇÃO DO CARRINHO ---------- */

function gvRenderCart() {
  const listEl = document.getElementById("cart-items");
  const totalItemsEl = document.getElementById("cart-total-items");
  const totalPriceEl = document.getElementById("cart-total-price");

  if (!listEl || !totalItemsEl || !totalPriceEl) {
    return;
  }

  const cart = gvLoadCart();

  listEl.innerHTML = "";

  if (cart.length === 0) {
    listEl.innerHTML =
      '<li class="cart-item cart-item-empty">Nenhum item no carrinho.</li>';
    totalItemsEl.textContent = "0";
    totalPriceEl.textContent = "€ 0";
    return;
  }

  let totalItems = 0;
  let totalPrice = 0;

  cart.forEach((item) => {
    totalItems += item.qty;
    totalPrice += item.price * item.qty;

    const li = document.createElement("li");
    li.className = "cart-item";

    li.innerHTML = `
      <div class="cart-item-main">
        <div class="cart-item-title">${item.name}</div>
        <div class="cart-item-meta">
          <span class="cart-item-qty">Qtd: ${item.qty}</span>
          <span class="cart-item-price">€ ${item.price.toLocaleString("pt-PT")}</span>
        </div>
      </div>
      <button class="cart-item-remove" data-remove-id="${item.id}" aria-label="Remover">
        ✕
      </button>
    `;

    listEl.appendChild(li);
  });

  totalItemsEl.textContent = String(totalItems);
  totalPriceEl.textContent = `€ ${totalPrice.toLocaleString("pt-PT")}`;

  // ligar botões de remover
  listEl.querySelectorAll("[data-remove-id]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-remove-id");
      if (id) gvRemoveFromCart(id);
    });
  });
}

/* ---------- INICIALIZAÇÃO NA PÁGINA LOJA ---------- */

document.addEventListener("DOMContentLoaded", () => {
  // Só corre na loja
  if (!document.body || document.body.getAttribute("data-page") !== "loja") {
    return;
  }

  // Render inicial
  gvRenderCart();

  // Botões "Adicionar ao pedido (demo)"
  document.querySelectorAll("[data-add-to-cart]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-product-id");
      const name = btn.getAttribute("data-product-name");
      const price = btn.getAttribute("data-product-price");

      if (!id || !name) return;

      gvAddToCart(id, name, price);
    });
  });

  // Botão "Limpar carrinho"
  const clearBtn = document.getElementById("cart-clear");
  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      if (confirm("Queres mesmo limpar o carrinho?")) {
        gvClearCart();
      }
    });
  }

  // Botão "Finalizar pedido (demo)"
  const checkoutBtn = document.getElementById("cart-checkout");
  if (checkoutBtn) {
    checkoutBtn.addEventListener("click", () => {
      const cart = gvLoadCart();
      if (!cart.length) {
        alert("O carrinho está vazio. Adiciona pelo menos um pacote.");
        return;
      }

      // Aqui, numa versão real, poderias:
      // - enviar o carrinho para o backend (/orders)
      // - redirecionar para uma página de resumo
      // Por enquanto, apenas mostramos um alerta.
      alert(
        "Demo: o pedido foi registado localmente.\n\n" +
          "Numa versão real, estes itens seriam enviados para a API GeoVision."
      );
    });
  }
});
