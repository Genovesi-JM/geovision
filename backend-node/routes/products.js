import express from 'express';
const router = express.Router();

// Sample product catalog
const PRODUCTS = [
  { id: 1, title: 'Inspeção Drone - Hectare', price: 120.0 },
  { id: 2, title: 'Mapeamento NDVI (parcel)', price: 240.0 },
  { id: 3, title: 'Monitor de rebanho - dispositivo', price: 45.0 }
];

// GET /api/products
router.get('/', (req, res) => {
  res.json({ products: PRODUCTS });
});

// GET /api/products/:id
router.get('/:id', (req, res) => {
  const id = Number(req.params.id);
  const p = PRODUCTS.find((x) => x.id === id);
  if (!p) return res.status(404).json({ detail: 'Product not found' });
  res.json(p);
});

export default router;
