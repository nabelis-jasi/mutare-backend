// middleware/roles.js
const allowRoles = (...allowedRoles) => (req, res, next) => {
  // Since req.user is now hardcoded in auth.js, this will always pass for 'engineer'
  if (allowedRoles.includes(req.user.role)) {
    return next();
  }
  res.status(403).json({ error: 'Access Denied' });
};

export default allowRoles;
