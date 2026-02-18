import { API_BASE } from "./config.js";

export async function checkout() {
    const token = localStorage.getItem("gv_token");
    const cart = JSON.parse(localStorage.getItem("cart") || "[]");

    if (!cart.length) {
        alert("Carrinho vazio.");
        return;
    }

    // 1 — Criar pedido
    const order = await fetch(`${API_BASE}/orders/create?user_id=1`, {
        method: "POST"
    }).then(r => r.json());

    // 2 — Adicionar itens ao pedido
    for (let item of cart) {
        await fetch(`${API_BASE}/orders/${order.id}/add`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                product_id: item.product_id,
                qty: item.qty
            })
        });
    }

    // 3 — Finalizar
    await fetch(`${API_BASE}/orders/${order.id}/checkout`, {
        method: "POST"
    });

    localStorage.removeItem("cart");
    alert("Pedido finalizado com sucesso!");
}
