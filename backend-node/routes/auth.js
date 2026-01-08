// assets/js/auth.js
// Login handler para GeoVision

document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("#login-form");
  const emailInput = document.querySelector("#username");
  const passwordInput = document.querySelector("#password");
  const msg = document.querySelector("#login-message");

  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const username = emailInput.value.trim();
    const password = passwordInput.value.trim();

    msg.textContent = "A verificar...";
    msg.style.color = "#ccc";

    try {
      // Enviar POST /api/auth/login
      const res = await fetch(`${API_BASE}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Credenciais inválidas");
      }

      const data = await res.json();
      const token = data.access_token;
      const user = data.user;

      if (!token || !user) throw new Error("Resposta inesperada do servidor.");

      // Guardar token e info do user
      localStorage.setItem("gv_token", token);
      localStorage.setItem("gv_user", JSON.stringify(user));

      msg.textContent = "Login com sucesso!";
      msg.style.color = "#4ade80";

      // Redirecionar conforme o e-mail
      const email = user.email.toLowerCase();

      if (email === "teste@demo.com") {
        window.location.href = "admin.html";
      } else if (email.endsWith("@cliente") || email.includes("cliente")) {
        window.location.href = "dashboard.html";
      } else {
        // Por defeito, dashboard normal
        window.location.href = "dashboard.html";
      }
    } catch (err) {
      msg.textContent = err.message || "Erro ao iniciar sessão.";
      msg.style.color = "#f87171";
    }
  });
});
