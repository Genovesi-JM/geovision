import express from 'express';
const router = express.Router();

let ORDERS = [];

// POST /api/orders  -> create order
router.post('/', (req, res) => {
  const { items, customer } = req.body;
  if (!items || !Array.isArray(items) || items.length === 0) {
    return res.status(400).json({ detail: 'Order must contain items' });
  }
  const id = ORDERS.length + 1;
  const order = { id, items, customer: customer || null, status: 'created', created_at: new Date() };
  ORDERS.push(order);
  res.status(201).json(order);
});

// GET /api/orders -> list orders
router.get('/', (req, res) => {
  res.json({ orders: ORDERS });
});

export default router;
