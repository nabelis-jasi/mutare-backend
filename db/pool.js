import pkg from 'pg';
const { Pool } = pkg;
import 'dotenv/config';

// Create the connection pool
const pool = new Pool({
  host: process.env.DB_HOST,
  port: process.env.DB_PORT,
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME,
  // Add SSL if you are connecting to a remote production DB like Render or AWS
  ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : false
});

// Test the connection logic (Optional but helpful for logs)
pool.on('connect', () => {
  console.log('🐘 PostgreSQL connected successfully');
});

pool.on('error', (err) => {
  console.error('❌ Unexpected error on idle client', err);
  process.exit(-1);
});

export default pool;
