-- GeoVision database schema (PostgreSQL)

-- ============ USERS / PERFIS ============

CREATE TABLE IF NOT EXISTS users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email         TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role          TEXT NOT NULL DEFAULT 'customer' CHECK (role IN ('customer','admin','staff')),
  is_active     BOOLEAN NOT NULL DEFAULT TRUE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_profiles (
  user_id       UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  full_name     TEXT,
  phone         TEXT,
  country       TEXT,
  city          TEXT,
  company       TEXT,
  nif           TEXT,
  avatar_url    TEXT,
  notes         TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_addresses (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  label         TEXT DEFAULT 'Default',
  line1         TEXT NOT NULL,
  line2         TEXT,
  city          TEXT NOT NULL,
  region        TEXT,
  postal_code   TEXT,
  country       TEXT NOT NULL,
  is_default    BOOLEAN NOT NULL DEFAULT FALSE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============ CATALOGO / STOCK ============

CREATE TABLE IF NOT EXISTS categories (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT UNIQUE NOT NULL,
  slug        TEXT UNIQUE NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS products (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sku           TEXT UNIQUE NOT NULL,
  name          TEXT NOT NULL,
  description   TEXT,
  category_id   UUID REFERENCES categories(id) ON DELETE SET NULL,
  brand         TEXT,
  unit          TEXT DEFAULT 'un',
  price         NUMERIC(12,2) NOT NULL CHECK (price >= 0),
  currency      TEXT NOT NULL DEFAULT 'AOA',
  is_active     BOOLEAN NOT NULL DEFAULT TRUE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS product_images (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id  UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  url         TEXT NOT NULL,
  is_primary  BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS inventory (
  product_id     UUID PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE,
  qty_on_hand    INTEGER NOT NULL DEFAULT 0 CHECK (qty_on_hand >= 0),
  qty_reserved   INTEGER NOT NULL DEFAULT 0 CHECK (qty_reserved >= 0),
  reorder_level  INTEGER NOT NULL DEFAULT 0 CHECK (reorder_level >= 0),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============ PEDIDOS / CHECKOUT ============

CREATE TABLE IF NOT EXISTS orders (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
  status          TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','paid','processing','shipped','delivered','cancelled','refunded')),
  currency        TEXT NOT NULL DEFAULT 'AOA',
  subtotal        NUMERIC(12,2) NOT NULL DEFAULT 0,
  shipping_fee    NUMERIC(12,2) NOT NULL DEFAULT 0,
  discount_total  NUMERIC(12,2) NOT NULL DEFAULT 0,
  total           NUMERIC(12,2) NOT NULL DEFAULT 0,
  shipping_address JSONB,
  notes           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS order_items (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id    UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  product_id  UUID REFERENCES products(id) ON DELETE SET NULL,
  sku         TEXT,
  name        TEXT,
  unit_price  NUMERIC(12,2) NOT NULL DEFAULT 0,
  qty         INTEGER NOT NULL CHECK (qty > 0),
  line_total  NUMERIC(12,2) NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
