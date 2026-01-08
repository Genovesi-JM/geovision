# GeoVision Node demo backend

This is a minimal Express demo backend providing simple routes used for frontend demos.

Install:

```bash
cd backend-node
npm install
```

Run:

```bash
npm start
# or for dev with auto-reload (if nodemon installed):
npm run dev
```

Endpoints:
- POST /api/auth/login { username, password }
- GET /api/auth/me
- GET /api/products
- GET /api/products/:id
- POST /api/orders
- GET /api/orders
- GET /api/users

This is intentionally simple and stores data in memory. Use for local demos only.
