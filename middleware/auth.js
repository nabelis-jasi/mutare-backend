/**
 * Mock Auth Middleware 
 * Automatically grants "Engineer" access to everyone.
 */
const auth = (req, res, next) => {
  req.user = { 
    id: 1, 
    username: 'engineer_admin', 
    role: 'engineer' 
  };
  next();
};

export default auth;
