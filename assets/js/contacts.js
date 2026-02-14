/**
 * GeoVision Contact Widget
 * Floating contact buttons (WhatsApp, Instagram, Email)
 * Loads contact methods from /contacts API and renders non-intrusively.
 * Does NOT alter existing layout or design.
 */
(function () {
  'use strict';

  const API_BASE = window.API_BASE || '';

  // Icons (inline SVG to avoid external dependencies)
  const ICONS = {
    whatsapp: `<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>`,
    instagram: `<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/></svg>`,
    email: `<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg>`,
    phone: `<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z"/></svg>`,
    contact: `<svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.17L4 17.17V4h16v12z"/><path d="M7 9h2v2H7zm4 0h2v2h-2zm4 0h2v2h-2z"/></svg>`
  };

  const CHANNEL_COLORS = {
    whatsapp: '#25D366',
    instagram: '#E4405F',
    email: '#2e86c1',
    phone: '#1a5276',
    sms: '#f39c12'
  };

  let contactsPanel = null;
  let isOpen = false;

  function injectStyles() {
    if (document.getElementById('gv-contacts-styles')) return;
    const style = document.createElement('style');
    style.id = 'gv-contacts-styles';
    style.textContent = `
      .gv-contact-fab {
        position: fixed; bottom: 90px; right: 24px; z-index: 9998;
        width: 50px; height: 50px; border-radius: 50%;
        background: linear-gradient(135deg, #1a5276, #2e86c1);
        color: #fff; border: none; cursor: pointer;
        box-shadow: 0 4px 12px rgba(0,0,0,0.25);
        display: flex; align-items: center; justify-content: center;
        transition: transform 0.2s, box-shadow 0.2s;
      }
      .gv-contact-fab:hover { transform: scale(1.1); box-shadow: 0 6px 20px rgba(0,0,0,0.3); }
      .gv-contact-panel {
        position: fixed; bottom: 150px; right: 24px; z-index: 9997;
        width: 280px; background: #fff; border-radius: 12px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.15);
        overflow: hidden; transform: translateY(20px) scale(0.95);
        opacity: 0; pointer-events: none;
        transition: transform 0.25s ease, opacity 0.25s ease;
      }
      .gv-contact-panel.open {
        transform: translateY(0) scale(1);
        opacity: 1; pointer-events: auto;
      }
      .gv-contact-panel-header {
        background: linear-gradient(135deg, #1a5276, #2e86c1);
        color: #fff; padding: 14px 18px; font-weight: 600; font-size: 14px;
      }
      .gv-contact-panel-body { padding: 8px 0; max-height: 320px; overflow-y: auto; }
      .gv-contact-item {
        display: flex; align-items: center; gap: 12px;
        padding: 10px 18px; text-decoration: none; color: #333;
        transition: background 0.15s; cursor: pointer; border: none;
        background: none; width: 100%; font-size: 13px; font-family: inherit;
      }
      .gv-contact-item:hover { background: #f0f4f8; }
      .gv-contact-icon {
        width: 36px; height: 36px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        color: #fff; flex-shrink: 0;
      }
      .gv-contact-info { flex: 1; text-align: left; }
      .gv-contact-label { font-weight: 600; font-size: 13px; color: #333; }
      .gv-contact-value { font-size: 11px; color: #888; margin-top: 2px; }
    `;
    document.head.appendChild(style);
  }

  function createWidget(contacts) {
    injectStyles();

    // FAB button
    const fab = document.createElement('button');
    fab.className = 'gv-contact-fab';
    fab.setAttribute('aria-label', 'Contactos');
    fab.title = 'Contactos';
    fab.innerHTML = ICONS.contact;
    fab.addEventListener('click', () => {
      isOpen = !isOpen;
      if (contactsPanel) contactsPanel.classList.toggle('open', isOpen);
    });

    // Panel
    contactsPanel = document.createElement('div');
    contactsPanel.className = 'gv-contact-panel';

    const header = document.createElement('div');
    header.className = 'gv-contact-panel-header';
    header.textContent = 'Fale Connosco';

    const body = document.createElement('div');
    body.className = 'gv-contact-panel-body';

    contacts.forEach(c => {
      const a = document.createElement('a');
      a.className = 'gv-contact-item';
      a.href = c.link || '#';
      a.target = '_blank';
      a.rel = 'noopener noreferrer';

      const iconDiv = document.createElement('div');
      iconDiv.className = 'gv-contact-icon';
      iconDiv.style.background = CHANNEL_COLORS[c.channel] || '#333';
      iconDiv.innerHTML = ICONS[c.channel] || ICONS.email;

      const info = document.createElement('div');
      info.className = 'gv-contact-info';

      const label = document.createElement('div');
      label.className = 'gv-contact-label';
      label.textContent = `${c.label} (${c.channel === 'whatsapp' ? 'WhatsApp' : c.channel === 'instagram' ? 'Instagram' : c.channel === 'email' ? 'Email' : c.channel.charAt(0).toUpperCase() + c.channel.slice(1)})`;

      const value = document.createElement('div');
      value.className = 'gv-contact-value';
      value.textContent = c.value;

      info.appendChild(label);
      info.appendChild(value);
      a.appendChild(iconDiv);
      a.appendChild(info);
      body.appendChild(a);
    });

    contactsPanel.appendChild(header);
    contactsPanel.appendChild(body);

    document.body.appendChild(contactsPanel);
    document.body.appendChild(fab);
  }

  async function loadContacts() {
    // Get user context for dynamic links
    const name = localStorage.getItem('gv_user') || '';
    const email = localStorage.getItem('gv_email') || '';

    let url = `${API_BASE}/contacts/?name=${encodeURIComponent(name)}&company=&context=`;

    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const contacts = await res.json();
      if (contacts.length > 0) {
        createWidget(contacts);
      }
    } catch (err) {
      // Fallback static contacts if API fails
      createWidget([
        { channel: 'whatsapp', label: 'Suporte', value: '+244 928 917 269', link: 'https://wa.me/244928917269?text=Ol%C3%A1%20GeoVision%2C%20preciso%20de%20ajuda.' },
        { channel: 'instagram', label: 'Instagram', value: '@Geovision.operations', link: 'https://instagram.com/Geovision.operations' },
        { channel: 'email', label: 'Suporte', value: 'support@geovisionops.com', link: 'mailto:support@geovisionops.com?subject=Contacto%20via%20GeoVision' },
      ]);
    }
  }

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadContacts);
  } else {
    loadContacts();
  }
})();
