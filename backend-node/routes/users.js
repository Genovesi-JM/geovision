import express from 'express';
const router = express.Router();

const USERS = [
  { id: 1, name: 'Demo User', email: 'teste@demo.com' }
];

// GET /api/users
router.get('/', (req, res) => {
  res.json({ users: USERS });
});

// GET /api/users/:id
router.get('/:id', (req, res) => {
  const id = Number(req.params.id);
  const u = USERS.find((x) => x.id === id);
  if (!u) return res.status(404).json({ detail: 'User not found' });
  res.json(u);
});

export default router;
