// node/scripts/initDb.js
// Run with: node scripts/initDb.js
// Creates the database and runs schema.sql

require('dotenv').config({ path: '../../.env' });
const { Pool } = require('pg');
const fs   = require('fs');
const path = require('path');

async function initDb() {
    console.log('\n🚀 Mutare Sewer Dashboard — Database Initializer\n');

    // Step 1: Connect to postgres (default db) to create our db if needed
    const adminPool = new Pool({
        host:     process.env.DB_HOST     || 'localhost',
        port:     parseInt(process.env.DB_PORT) || 5432,
        database: 'postgres',   // connect to default DB first
        user:     process.env.DB_USER     || 'postgres',
        password: process.env.DB_PASSWORD || '',
    });

    const dbName = process.env.DB_NAME || 'blue';

    try {
        // Check if our database already exists
        const check = await adminPool.query(
            `SELECT 1 FROM pg_database WHERE datname = $1`, [dbName]
        );

        if (check.rows.length === 0) {
            console.log(`📦 Creating database "${dbName}"...`);
            await adminPool.query(`CREATE DATABASE ${dbName}`);
            console.log(`✅ Database "${dbName}" created`);
        } else {
            console.log(`✅ Database "${dbName}" already exists`);
        }
    } catch (err) {
        console.error('❌ Failed to create database:', err.message);
        process.exit(1);
    } finally {
        await adminPool.end();
    }

    // Step 2: Connect to our database and run schema
    const appPool = new Pool({
        host:     process.env.DB_HOST     || 'localhost',
        port:     parseInt(process.env.DB_PORT) || 5432,
        database: dbName,
        user:     process.env.DB_USER     || 'postgres',
        password: process.env.DB_PASSWORD || '',
    });

    try {
        // Check PostGIS
        console.log('\n🔌 Checking PostGIS extension...');
        try {
            await appPool.query('CREATE EXTENSION IF NOT EXISTS postgis');
            console.log('✅ PostGIS enabled');
        } catch (err) {
            console.error('❌ PostGIS not available:', err.message);
            console.log('   Install with: sudo apt install postgresql-postgis');
            console.log('   or on Windows: include PostGIS in the installer');
            process.exit(1);
        }

        // Run schema
        const schemaPath = path.join(__dirname, '../../schema.sql');
        if (!fs.existsSync(schemaPath)) {
            console.error('❌ schema.sql not found at:', schemaPath);
            process.exit(1);
        }

        console.log('\n📋 Running schema.sql...');
        const sql = fs.readFileSync(schemaPath, 'utf8');

        // Split on semicolons but keep statements together
        // (schema.sql has multi-line statements)
        await appPool.query(sql);
        console.log('✅ Schema applied successfully');

        // Step 3: Verify tables
        console.log('\n🔍 Verifying tables...');
        const tables = await appPool.query(`
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
        `);
        tables.rows.forEach(t => console.log(`   ✓ ${t.tablename}`));

        // Step 4: Show row counts
        console.log('\n📊 Seeded data:');
        const counts = await appPool.query(`
            SELECT
                (SELECT COUNT(*) FROM waste_water_manhole)  AS manholes,
                (SELECT COUNT(*) FROM waste_water_pipeline) AS pipelines,
                (SELECT COUNT(*) FROM suburbs)              AS suburbs,
                (SELECT COUNT(*) FROM job_logs)             AS jobs
        `);
        const c = counts.rows[0];
        console.log(`   Manholes:  ${c.manholes}`);
        console.log(`   Pipelines: ${c.pipelines}`);
        console.log(`   Suburbs:   ${c.suburbs}`);
        console.log(`   Jobs:      ${c.jobs}`);

        console.log('\n🎉 Database ready! You can now start the servers.\n');
        console.log('   Node.js:  cd node && npm run dev');
        console.log('   Python:   cd python && python app.py\n');

    } catch (err) {
        console.error('❌ Schema error:', err.message);
        console.error(err);
        process.exit(1);
    } finally {
        await appPool.end();
    }
}

initDb();
