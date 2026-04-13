const { Pool } = require('pg');
const centralPool = require('../db/pool');

/**
 * Get a PostgreSQL connection pool for the user's active connection
 * This allows each engineer to query their own local database
 */
async function getUserConnectionPool(userId) {
    try {
        // Get the user's active connection
        const result = await centralPool.query(
            `SELECT pg_host, pg_port, pg_database, pg_user, pg_password 
             FROM connections 
             WHERE user_id = $1 AND is_active = true`,
            [userId]
        );
        
        if (result.rows.length === 0) {
            return null;
        }
        
        const conn = result.rows[0];
        
        // Create a new pool for this user's local database
        return new Pool({
            host: conn.pg_host,
            port: conn.pg_port,
            database: conn.pg_database,
            user: conn.pg_user,
            password: conn.pg_password,
            // Connection pool settings
            max: 5,
            idleTimeoutMillis: 30000,
            connectionTimeoutMillis: 10000,
        });
    } catch (err) {
        console.error('Error getting user connection pool:', err);
        return null;
    }
}

/**
 * Execute a query on the user's local database
 */
async function queryUserDatabase(userId, queryText, params = []) {
    const pool = await getUserConnectionPool(userId);
    if (!pool) {
        throw new Error('No active database connection. Please configure a connection in the Connections panel.');
    }
    
    try {
        const result = await pool.query(queryText, params);
        return result;
    } finally {
        // Don't end the pool - reuse it for subsequent queries
        // Just release the client back to the pool
    }
}

module.exports = {
    getUserConnectionPool,
    queryUserDatabase
};
