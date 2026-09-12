const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const root = path.resolve(__dirname, '../..');
const sessionSource = fs.readFileSync(path.join(root, 'assets/js/session.js'), 'utf8');
const authSource = fs.readFileSync(path.join(root, 'assets/js/auth.js'), 'utf8');
const callbackSource = fs.readFileSync(path.join(root, 'auth-callback.html'), 'utf8')
  .match(/<script>\s*([\s\S]*?)<\/script>/)[1];

test('login and OAuth load the shared session helper before their auth code', () => {
  const login = fs.readFileSync(path.join(root, 'login.html'), 'utf8');
  const callback = fs.readFileSync(path.join(root, 'auth-callback.html'), 'utf8');
  assert.ok(login.indexOf('assets/js/session.js?v=2') > 0);
  assert.ok(login.indexOf('assets/js/session.js?v=2') < login.indexOf('assets/js/auth.js?v=10'));
  assert.ok(callback.indexOf('assets/js/config.js') < callback.indexOf('assets/js/session.js?v=2'));
  assert.ok(callback.indexOf('assets/js/session.js?v=2') < callback.indexOf('(async function(){'));
});

function storage() {
  const values = new Map();
  return { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, String(value)), removeItem: key => values.delete(key) };
}

function element() {
  const handlers = {};
  const children = new Map();
  return {
    handlers, children, style: {}, dataset: {}, textContent: '', innerHTML: '', value: '', disabled: false,
    classList: { toggle: () => true, remove() {} },
    addEventListener(event, handler) { handlers[event] = handler; },
    setAttribute() {}, focus() {}, appendChild() {}, contains: () => false,
    querySelector(selector) { if (!children.has(selector)) children.set(selector, element()); return children.get(selector); },
    querySelectorAll: () => [],
    replaceWith(replacement) { this.replacement = replacement; },
  };
}

function fixture({ pathname = '/login.html', portal = false, fetchResponse, search = '' } = {}) {
  const localStorage = storage();
  const sessionStorage = storage();
  const callbacks = [];
  const portalLink = portal ? element() : null;
  const nodes = { 'login-form': element(), 'login-email': element(), 'login-password': element(), 'login-submit': element(), 'error-box': element(), 'success-box': element(), msg: element() };
  const requests = [];
  const location = { pathname, search, hash: '', href: `https://pilot.example.test${pathname}${search}`, replace(value) { this.redirect = value; } };
  const context = vm.createContext({
    localStorage, sessionStorage, URL, URLSearchParams, AbortController, setTimeout, clearTimeout,
    window: { API_BASE: 'https://api.example.test', location },
    history: { replaceState(_state, _title, url) { location.cleaned = url; } },
    document: { head: element(), createElement: element, addEventListener: (event, handler) => { if (event === 'DOMContentLoaded') callbacks.push(handler); }, querySelector: () => portalLink, getElementById: id => nodes[id] || null },
    fetch: async (url, options) => {
      requests.push({ url, options });
      return fetchResponse ? fetchResponse(url, options) : { ok: true, status: 200, json: async () => profile() };
    },
  });
  vm.runInContext(sessionSource, context);
  return { context, api: context.window.GV.session, localStorage, sessionStorage, callbacks, portalLink, nodes, requests, location };
}

function profile(overrides = {}) {
  return {
    id: 'staff-1', email: 'staff@example.test', name: '', role: 'cliente', account: null,
    account_id: '', account_name: '', company_id: '',
    authorization_context: { user_id: 'staff-1', internal_roles: ['GV_OPERATIONS'], permissions: ['operations:access'] },
    ...overrides,
  };
}

function priorCustomer(fixture) {
  fixture.localStorage.setItem('gv_user', JSON.stringify({ id: 'customer-old' }));
  for (const key of ['gv_token', 'gv_refresh_token', 'gv_name', 'gv_role', 'gv_email', 'gv_account_id', 'gv_account_name', 'gv_workspace_id', 'gv_organization_id', 'gv_active_sector']) fixture.localStorage.setItem(key, `old-${key}`);
  fixture.sessionStorage.setItem('gv_portal_return', '/dashboard.html?asset=old-asset');
  fixture.localStorage.setItem('gv_lang', 'es');
}

test('staff sign-in replaces stale customer identity/workspace but preserves invitation and preferences', () => {
  const f = fixture(); priorCustomer(f);
  f.sessionStorage.setItem('gv_pending_invitation', 'explicit invitation');
  f.api.persist('new-access-only', profile());
  for (const key of ['gv_refresh_token', 'gv_name', 'gv_account_id', 'gv_account_name', 'gv_workspace_id', 'gv_organization_id', 'gv_active_sector']) assert.equal(f.localStorage.getItem(key), null, key);
  assert.equal(f.sessionStorage.getItem('gv_portal_return'), null);
  assert.equal(f.sessionStorage.getItem('gv_pending_invitation'), 'explicit invitation');
  assert.equal(f.localStorage.getItem('gv_lang'), 'es');
  assert.equal(f.localStorage.getItem('gv_token'), 'new-access-only');
  assert.equal(f.localStorage.getItem('gv_role'), 'cliente');
  assert.equal(JSON.parse(f.localStorage.getItem('gv_user')).id, 'staff-1');
});

test('null account overrides contradictory legacy account fields', () => {
  const f = fixture(); priorCustomer(f);
  f.api.persist('new', profile({ account_id: 'stale', account_name: 'stale', company_id: 'stale' }));
  assert.equal(f.localStorage.getItem('gv_account_id'), null);
  assert.equal(f.localStorage.getItem('gv_organization_id'), null);
});

test('an explicitly assigned account is retained for staff or customers', () => {
  const f = fixture(); priorCustomer(f);
  f.api.persist('new', profile({ account: { id: 'assigned-workspace', name: 'Assigned workspace' }, company_id: 'assigned-org' }));
  assert.equal(f.localStorage.getItem('gv_account_id'), 'assigned-workspace');
  assert.equal(f.localStorage.getItem('gv_workspace_id'), 'assigned-workspace');
  assert.equal(f.localStorage.getItem('gv_account_name'), 'Assigned workspace');
  assert.equal(f.localStorage.getItem('gv_organization_id'), 'assigned-org');
  assert.equal(f.localStorage.getItem('gv_active_sector'), null);
});

test('public session refresh does not overwrite an explicit customer workspace selection', () => {
  const f = fixture();
  f.localStorage.setItem('gv_user', JSON.stringify({ id: 'staff-1' }));
  f.localStorage.setItem('gv_workspace_id', 'selected-workspace-b');
  f.localStorage.setItem('gv_account_id', 'selected-workspace-b');
  f.api.persist('same-token', profile({ account: { id: 'default-workspace-a' } }), { replaceContext: false });
  assert.equal(f.localStorage.getItem('gv_workspace_id'), 'selected-workspace-b');
  assert.equal(f.localStorage.getItem('gv_account_id'), 'selected-workspace-b');
});

test('only canonical server internal roles select the staff landing page', () => {
  const f = fixture();
  assert.equal(f.api.dashboardUrl(profile()), 'admin.html');
  assert.equal(f.api.dashboardUrl(profile({ role: 'admin', authorization_context: { internal_roles: [] } })), 'dashboard.html');
  assert.equal(f.api.dashboardUrl(profile({ role: 'GV_SUPER_ADMIN', authorization_context: { internal_roles: ['GV_UNKNOWN'] } })), 'dashboard.html');
  assert.equal(f.api.dashboardUrl(profile({ authorization_context: null })), 'dashboard.html');
});

test('safe customer/contractor deep links and invitations retain priority', () => {
  const f = fixture();
  for (const value of ['/dashboard.html?asset=existing', 'contractor.html?view=jobs', '/onboarding.html', 'loja.html']) assert.equal(f.api.destination(profile(), value), value);
  f.sessionStorage.setItem('gv_pending_invitation', 'pending & token');
  assert.equal(f.api.destination(profile(), '/admin.html'), 'onboarding.html#invitation=pending%20%26%20token');
});

test('external and parser-ambiguous return locations fail closed', () => {
  const f = fixture();
  for (const value of ['https://evil.test', '//evil.test', '/\\evil.test', '/%2f%2fevil.test', 'javascript:alert(1)', '/admin.html\n//evil.test', '/admin.html/../evil', ' admin.html', '/unrecognized.html']) assert.equal(f.api.destination(profile(), value), 'admin.html', value);
});

test('profile verification uses only its bearer and rejects cross-user response', async () => {
  const f = fixture();
  assert.equal((await f.api.verify('test-access', { id: 'staff-1', email: 'STAFF@example.test' })).id, 'staff-1');
  const { url, options } = f.requests[0];
  assert.equal(url, 'https://api.example.test/auth/me');
  assert.equal(options.headers.Authorization, 'Bearer test-access');
  assert.equal(options.credentials, 'omit');
  assert.equal(options.cache, 'no-store');
  assert.equal(options.redirect, 'error');
  await assert.rejects(f.api.verify('test-access', { id: 'someone-else' }), /Perfil/);
  await assert.rejects(f.api.verify('test-access', { email: 'someone-else@example.test' }), /Perfil/);
});

test('mismatched authorization subject and invalid identity are rejected', async () => {
  for (const invalid of [profile({ id: '' }), profile({ email: null }), profile({ role: '' }), profile({ authorization_context: { user_id: 'other', internal_roles: ['GV_SUPER_ADMIN'] } })]) {
    const f = fixture({ fetchResponse: async () => ({ ok: true, json: async () => invalid }) });
    await assert.rejects(f.api.verify('access'), /Perfil/);
  }
});

test('public menu uses the verified identity, escapes display names and routes staff', async () => {
  const f = fixture({ portal: true, fetchResponse: async () => ({ ok: true, json: async () => profile({ name: '<img src=x onerror=alert(1)>' }) }) }); priorCustomer(f);
  await f.context.window.GV.initSession();
  assert.match(f.portalLink.replacement.innerHTML, /&lt;img/);
  assert.doesNotMatch(f.portalLink.replacement.innerHTML, /<img/);
  assert.match(f.portalLink.replacement.innerHTML, /href="admin.html"/);
  assert.equal(f.location.redirect, 'admin.html');
  assert.equal(f.localStorage.getItem('gv_account_id'), null);
});

test('expired public session clears identity/context without losing a pending invitation', async () => {
  const f = fixture({ portal: true, fetchResponse: async () => ({ ok: false, status: 401 }) }); priorCustomer(f);
  f.sessionStorage.setItem('gv_pending_invitation', 'invite');
  await f.context.window.GV.initSession();
  assert.equal(f.localStorage.getItem('gv_token'), null);
  assert.equal(f.localStorage.getItem('gv_workspace_id'), null);
  assert.equal(f.sessionStorage.getItem('gv_pending_invitation'), 'invite');
  assert.equal(f.portalLink.replacement, undefined);
  assert.equal(f.location.redirect, undefined);
});

test('network error does not show unverified identity or erase a valid cached token', async () => {
  const f = fixture({ portal: true, fetchResponse: async () => { throw new Error('network unavailable'); } }); priorCustomer(f);
  await f.context.window.GV.initSession();
  assert.equal(f.localStorage.getItem('gv_token'), 'old-gv_token');
  assert.equal(f.portalLink.replacement, undefined);
  assert.equal(f.location.redirect, undefined);
});

test('an older profile response cannot overwrite a newer login', async () => {
  let complete;
  const f = fixture({ portal: true, fetchResponse: () => new Promise(resolve => { complete = resolve; }) }); priorCustomer(f);
  const pending = f.context.window.GV.initSession();
  f.api.persist('newer-login-token', profile({ id: 'newer-user' }));
  complete({ ok: true, json: async () => profile() });
  await pending;
  assert.equal(f.localStorage.getItem('gv_token'), 'newer-login-token');
  assert.equal(JSON.parse(f.localStorage.getItem('gv_user')).id, 'newer-user');
  assert.equal(f.portalLink.replacement, undefined);
});

test('logout clears customer context and invitation without touching preferences', async () => {
  const f = fixture({ portal: true }); priorCustomer(f);
  f.sessionStorage.setItem('gv_pending_invitation', 'invite');
  await f.context.window.GV.initSession();
  f.portalLink.replacement.querySelector('#gv-logout-btn').handlers.click();
  assert.equal(f.localStorage.getItem('gv_token'), null);
  assert.equal(f.localStorage.getItem('gv_workspace_id'), null);
  assert.equal(f.sessionStorage.getItem('gv_pending_invitation'), null);
  assert.equal(f.localStorage.getItem('gv_lang'), 'es');
});

test('password login persists only the separately verified profile and chooses staff operations', async () => {
  const f = fixture({ fetchResponse: async url => url.endsWith('/auth/login')
    ? { ok: true, json: async () => ({ access_token: 'signed-in-token', refresh_token: 'ignore-me', user: { id: 'staff-1', email: 'staff@example.test', role: 'cliente' }, account: null }) }
    : { ok: true, json: async () => profile() } }); priorCustomer(f);
  vm.runInContext(authSource, f.context);
  f.callbacks.at(-1)();
  f.nodes['login-email'].value = 'staff@example.test';
  f.nodes['login-password'].value = 'synthetic-offline-test';
  await f.nodes['login-form'].handlers.submit({ preventDefault() {} });
  assert.deepEqual(f.requests.map(request => request.url), ['https://api.example.test/auth/login', 'https://api.example.test/auth/me']);
  assert.equal(f.localStorage.getItem('gv_token'), 'signed-in-token');
  assert.equal(f.localStorage.getItem('gv_refresh_token'), null);
  assert.equal(f.localStorage.getItem('gv_workspace_id'), null);
  assert.equal(f.location.href, 'admin.html');
});

test('failed post-login verification never stores the returned token or redirects', async () => {
  const f = fixture({ fetchResponse: async url => url.endsWith('/auth/login')
    ? { ok: true, json: async () => ({ access_token: 'unverified-token', user: { id: 'staff-1', email: 'staff@example.test' } }) }
    : { ok: false, status: 401 } });
  vm.runInContext(authSource, f.context);
  f.callbacks.at(-1)();
  f.nodes['login-email'].value = 'staff@example.test';
  f.nodes['login-password'].value = 'synthetic-offline-test';
  await f.nodes['login-form'].handlers.submit({ preventDefault() {} });
  assert.equal(f.localStorage.getItem('gv_token'), null);
  assert.equal(f.location.href, 'https://pilot.example.test/login.html');
  assert.match(f.nodes['error-box'].textContent, /validar/);
});

test('OAuth callback removes stale context and does not trust fragment identity or legacy customer redirect', async () => {
  const f = fixture({ pathname: '/auth-callback.html' }); priorCustomer(f);
  f.sessionStorage.setItem('gv_oauth_nonce_google', 'matching-nonce');
  f.location.hash = '#token=oauth-token&refresh_token=ignored&provider=google&browser_nonce=matching-nonce&role=admin&email=forged@example.test&redirect=%2Fonboarding.html';
  await vm.runInContext(callbackSource, f.context);
  assert.equal(f.localStorage.getItem('gv_token'), 'oauth-token');
  assert.equal(f.localStorage.getItem('gv_refresh_token'), null);
  assert.equal(f.localStorage.getItem('gv_workspace_id'), null);
  assert.equal(f.localStorage.getItem('gv_email'), 'staff@example.test');
  assert.equal(f.location.cleaned, '/auth-callback.html');
  assert.equal(f.location.redirect, 'https://pilot.example.test/admin.html');
});

test('OAuth customer return keeps explicit account and rejects fragment privilege claims', async () => {
  const f = fixture({ pathname: '/auth-callback.html', fetchResponse: async () => ({ ok: true, json: async () => profile({
    authorization_context: { user_id: 'staff-1', internal_roles: [] }, account: { id: 'customer-workspace', name: 'Customer' },
  }) }) }); priorCustomer(f);
  f.sessionStorage.setItem('gv_oauth_nonce_microsoft', 'matching-nonce');
  f.location.hash = '#token=oauth-token&provider=microsoft&browser_nonce=matching-nonce&role=admin&redirect=https://evil.test';
  await vm.runInContext(callbackSource, f.context);
  assert.equal(f.localStorage.getItem('gv_workspace_id'), 'customer-workspace');
  assert.equal(f.location.redirect, 'https://pilot.example.test/dashboard.html');
});

test('OAuth staff still land in an explicitly pending invitation', async () => {
  const f = fixture({ pathname: '/auth-callback.html' }); priorCustomer(f);
  f.sessionStorage.setItem('gv_oauth_nonce_google', 'matching-nonce');
  f.sessionStorage.setItem('gv_pending_invitation', 'an invitation');
  f.location.hash = '#token=oauth-token&provider=google&browser_nonce=matching-nonce&redirect=%2Fadmin.html';
  await vm.runInContext(callbackSource, f.context);
  assert.equal(f.location.redirect, 'https://pilot.example.test/onboarding.html#invitation=an%20invitation');
  assert.equal(f.localStorage.getItem('gv_account_id'), null);
});
