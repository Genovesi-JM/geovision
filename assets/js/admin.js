// assets/js/admin.js

const API_BASE = (typeof window !== 'undefined' && window.API_BASE) ? window.API_BASE : 'http://127.0.0.1:8010';

function adminAuthHeaders() {
  const token = localStorage.getItem('gv_token');
  const accountId = localStorage.getItem('gv_account_id');
  const h = { 'Content-Type': 'application/json' };
  if (token) h['Authorization'] = `Bearer ${token}`;
  if (accountId) h['X-Account-ID'] = accountId;
  return h;
}

let products = [];

function requireAdmin() {
  const token = localStorage.getItem("gv_token");
  const role = localStorage.getItem("gv_role");
  const email = localStorage.getItem("gv_email") || "—";

  document.getElementById("admin-email").textContent = email;

  if (!token || role !== "admin") {
    alert("Acesso restrito a administradores.");
    window.location.href = "login.html";
  }
}

async function fetchProducts() {
  const res = await fetch(`${API_BASE}/products/`, {
    headers: adminAuthHeaders(),
  });
  if (!res.ok) {
    throw new Error("Falha ao carregar produtos");
  }
  products = await res.json();
}

function renderProductsTable() {
  const tbody = document.querySelector("#products-table tbody");
  const empty = document.getElementById("products-empty");
  tbody.innerHTML = "";

  if (!products.length) {
    empty.style.display = "block";
    return;
  } else {
    empty.style.display = "none";
  }

  products.forEach((p) => {
    const tr = document.createElement("tr");

    const price = Number(p.price || 0).toFixed(2);
    const badgeClass = p.active ? "admin-badge active" : "admin-badge inactive";
    const badgeText = p.active ? "Ativo" : "Inativo";

    tr.innerHTML = `
      <td>${p.name}</td>
      <td>${p.category}</td>
      <td>${price} €</td>
      <td>${p.unit || "-"}</td>
      <td><span class="${badgeClass}">${badgeText}</span></td>
      <td class="admin-actions">
        <button onclick="editProduct(${p.id})">Editar</button>
        <button onclick="deleteProduct(${p.id})">Apagar</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function fillForm(product) {
  document.getElementById("product-id").value = product.id;
  document.getElementById("name").value = product.name;
  document.getElementById("category").value = product.category;
  document.getElementById("price").value = Number(product.price).toFixed(2);
  document.getElementById("unit").value = product.unit || "";
  document.getElementById("description").value = product.description || "";
  document.getElementById("active").checked = product.active;
}

function resetForm() {
  document.getElementById("product-id").value = "";
  document.getElementById("name").value = "";
  document.getElementById("category").value = "servico-agricultura";
  document.getElementById("price").value = "";
  document.getElementById("unit").value = "";
  document.getElementById("description").value = "";
  document.getElementById("active").checked = true;
}

async function saveProduct(e) {
  e.preventDefault();

  const id = document.getElementById("product-id").value;
  const payload = {
    name: document.getElementById("name").value,
    category: document.getElementById("category").value,
    price: parseFloat(document.getElementById("price").value || "0"),
    unit: document.getElementById("unit").value || null,
    description: document.getElementById("description").value || null,
    active: document.getElementById("active").checked,
  };

  const method = id ? "PUT" : "POST";
  const url = id ? `${API_BASE}/products/${id}` : `${API_BASE}/products/`;

  const res = await fetch(url, {
    method,
    headers: adminAuthHeaders(),
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    alert("Falha ao guardar produto.");
    return;
  }

  await loadAndRender();
  resetForm();
}

async function deleteProduct(id) {
  if (!confirm("Tem a certeza que quer apagar este produto?")) return;

  const res = await fetch(`${API_BASE}/products/${id}`, {
    method: "DELETE",
    headers: adminAuthHeaders(),
  });

  if (!res.ok) {
    alert("Não foi possível apagar o produto.");
    return;
  }

  await loadAndRender();
}

function editProduct(id) {
  const p = products.find((x) => x.id === id);
  if (!p) return;
  fillForm(p);
}

// Expor algumas funções
window.editProduct = editProduct;
window.deleteProduct = deleteProduct;

async function loadAndRender() {
  await fetchProducts();
  renderProductsTable();
}

document.addEventListener("DOMContentLoaded", () => {
  requireAdmin();
  loadAndRender();

  document.getElementById("product-form").addEventListener("submit", saveProduct);
  document.getElementById("btn-reset").addEventListener("click", resetForm);

  document.getElementById("btn-admin-logout").addEventListener("click", () => {
    localStorage.removeItem("gv_token");
    localStorage.removeItem("gv_role");
    localStorage.removeItem("gv_email");
    localStorage.removeItem("gv_user");
    localStorage.removeItem("gv_account_id");
    window.location.href = "index.html";
  });
});
