#!/usr/bin/env python3
"""Script to update loja.html cart panel for new shop API."""
import re

FILE_PATH = r"c:\Users\Genov\OneDrive\Desktop\geovision\loja.html"

with open(FILE_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# Match the old cart total and form section
# Note: €\xa0 is euro with non-breaking space
old_cart_total_and_form = """<div class="loja-cart-total">
          <span>Total estimado</span>
          <strong id="cart-total">€\xa00,00</strong>
        </div>

        <div class="cart-form">
          <label for="checkout-name">Nome</label>
          <input type="text" id="checkout-name" placeholder="Ex.: Joana M." />

          <label for="checkout-company">Empresa / Fazenda</label>
          <input type="text" id="checkout-company" placeholder="Opcional" />

          <label for="checkout-email">Email</label>
          <input type="email" id="checkout-email" placeholder="cliente@empresa.co.ao" required />

          <label for="checkout-phone">Telefone</label>
          <input type="text" id="checkout-phone" placeholder="+244 ..." />

          <label for="checkout-notes">Notas adicionais</label>
          <textarea id="checkout-notes" rows="3" placeholder="Ex.: missão em Benguela, urgência em 30 dias"></textarea>
        </div>

        <div class="loja-cart-buttons">
          <button id="cart-clear" class="btn-sm">Limpar carrinho</button>
          <button id="cart-checkout" class="btn-sm btn-sm-primary">
            Enviar pedido
          </button>
        </div>

        <p class="form-hint">
          Os itens e dados acima são enviados ao backend FastAPI local para gerar um pedido de demonstração.
        </p>"""

new_cart_section = """<div class="coupon-row">
          <input type="text" id="coupon-input" class="coupon-input" placeholder="Código de cupão" />
          <button id="apply-coupon" class="btn-sm">Aplicar</button>
        </div>
        <div id="coupon-status" class="coupon-applied" style="display:none;"></div>

        <div class="loja-cart-total">
          <span>Subtotal</span>
          <strong id="cart-subtotal">0 AOA</strong>
        </div>
        <div class="loja-cart-total" id="discount-row" style="display:none;">
          <span>Desconto</span>
          <strong id="cart-discount" style="color:#22c55e;">-0 AOA</strong>
        </div>
        <div class="loja-cart-total" id="tax-row" style="display:none;">
          <span>IVA (14%)</span>
          <strong id="cart-tax">0 AOA</strong>
        </div>
        <div class="loja-cart-total" style="border-top:1px solid rgba(148,163,184,0.3);padding-top:0.4rem;margin-top:0.3rem;">
          <span><strong>Total</strong></span>
          <strong id="cart-total">0 AOA</strong>
        </div>

        <div class="loja-cart-buttons">
          <button id="cart-clear" class="btn-sm">Limpar</button>
          <button id="cart-checkout" class="btn-sm btn-sm-primary">Checkout</button>
        </div>

        <p class="form-hint" style="font-size:0.72rem;color:#9ca3af;margin-top:0.6rem;">
          Cupões demo: WELCOME10 (10% off), DRONE50K (50.000 AOA off)
        </p>"""

# Step 1: Replace the cart section
if old_cart_total_and_form in content:
    content = content.replace(old_cart_total_and_form, new_cart_section)
    print("Step 1: Cart panel replaced!")
else:
    print("Step 1: Cart panel pattern not found - checking variants...")
    # Try with regular space instead of nbsp
    alt_pattern = old_cart_total_and_form.replace('\xa0', ' ')
    if alt_pattern in content:
        content = content.replace(alt_pattern, new_cart_section)
        print("Step 1: Cart panel replaced (with regular space)!")
    else:
        print("Step 1: Could not find cart panel pattern")

# Step 2: Replace old loja.js with loja-shop.js at the end
old_script = '<script src="assets/js/loja.js"></script>'
new_script = '<script src="assets/js/loja-shop.js"></script>'

if old_script in content:
    content = content.replace(old_script, new_script)
    print("Step 2: Script replaced!")
else:
    print("Step 2: Old script not found")

# Step 3: Add checkout modal before </body>
checkout_modal = '''
  <!-- Checkout Modal -->
  <div id="checkout-modal" class="checkout-modal">
    <div class="checkout-modal-content">
      <div class="checkout-header">
        <h3 class="checkout-title">Finalizar Compra</h3>
        <button class="checkout-close" onclick="closeCheckoutModal()">×</button>
      </div>
      
      <div id="checkout-content">
        <div class="checkout-section">
          <h4>Dados de Faturação</h4>
          <input type="text" id="billing-name" class="checkout-input" placeholder="Nome completo" required />
          <input type="email" id="billing-email" class="checkout-input" placeholder="Email" required />
          <input type="text" id="billing-phone" class="checkout-input" placeholder="Telefone (+244...)" />
          <input type="text" id="billing-company" class="checkout-input" placeholder="Empresa (opcional)" />
          <input type="text" id="billing-nif" class="checkout-input" placeholder="NIF (opcional)" />
        </div>

        <div class="checkout-section">
          <h4>Método de Pagamento</h4>
          <div class="payment-methods">
            <label class="payment-option" onclick="selectPayment('multicaixa_express')">
              <input type="radio" name="payment" value="multicaixa_express" checked />
              <div>
                <div class="payment-label">Multicaixa Express</div>
                <div class="payment-desc">Pagamento por QR code ou referência</div>
              </div>
            </label>
            <label class="payment-option" onclick="selectPayment('visa_mastercard')">
              <input type="radio" name="payment" value="visa_mastercard" />
              <div>
                <div class="payment-label">Visa / Mastercard</div>
                <div class="payment-desc">Cartão de crédito/débito internacional</div>
              </div>
            </label>
            <label class="payment-option" onclick="selectPayment('iban_angola')">
              <input type="radio" name="payment" value="iban_angola" />
              <div>
                <div class="payment-label">Transferência IBAN (Angola)</div>
                <div class="payment-desc">Transferência bancária local AOA</div>
              </div>
            </label>
            <label class="payment-option" onclick="selectPayment('iban_international')">
              <input type="radio" name="payment" value="iban_international" />
              <div>
                <div class="payment-label">Transferência IBAN (Internacional)</div>
                <div class="payment-desc">SWIFT/SEPA em EUR</div>
              </div>
            </label>
          </div>
        </div>

        <div class="checkout-section">
          <h4>Resumo do Pedido</h4>
          <div class="checkout-summary" id="checkout-summary">
            <!-- Filled by JS -->
          </div>
        </div>

        <button class="checkout-btn" id="confirm-checkout-btn" onclick="processCheckout()">
          Confirmar Pedido
        </button>
      </div>

      <div id="payment-instructions" style="display:none;">
        <!-- Payment instructions filled by JS -->
      </div>
    </div>
  </div>

'''

if '</body>' in content and '<div id="checkout-modal"' not in content:
    content = content.replace('</body>', checkout_modal + '</body>')
    print("Step 3: Checkout modal added!")
else:
    if '<div id="checkout-modal"' in content:
        print("Step 3: Checkout modal already exists")
    else:
        print("Step 3: Could not find </body> tag")

# Write the updated content
with open(FILE_PATH, 'w', encoding='utf-8') as f:
    f.write(content)

print("\nDone! File updated.")
