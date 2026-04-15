/**
 * Role-based access control middleware
 * Corrected for ES Module usage (Node.js "type": "module")
 */
const allowRoles = (...allowedRoles) => (req, res, next) => {
  if (!req.user) {
    return res.status(401).json({ error: 'Unauthenticated' });
  }

  if (!allowedRoles.includes(req.user.role)) {
    return res.status(403).json({ error: 'Insufficient permissions' });
  }

  next();
};

export default allowRoles;
