const { Pool } = require('pg');

// We use a function so we can pass the user's specific credentials later
const createConnection = (config) => {
  return new Pool({
    user: config.user,
    host: config.host,
    database: config.database,
    password: config.password,
    port: config.port || 5432,
  });
};

module.exports = { createConnection };
