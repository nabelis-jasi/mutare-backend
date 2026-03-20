import express from "express";
import cors from "cors";
import { Pool } from "pg";
import dotenv from "dotenv";

dotenv.config();

const app = express();
app.use(cors());
app.use(express.json());

app.get("/", (req, res) => {
  res.json({ message: "API running", endpoints: ["/manholes"] });
});

let pool: Pool | null = null;

async function initDb() {
  const conn = process.env.DATABASE_URL;
  if (!conn) {
    console.warn("DATABASE_URL not set. Starting server without DB connection.");
    return;
  }

  try {
    pool = new Pool({ connectionString: conn, ssl: { rejectUnauthorized: false } });
    await pool.query("SELECT 1");
    console.log("Connected to database");
  } catch (err) {
    console.error("Database connection failed:", (err as Error).message || err);
    pool = null;
  }
}

initDb();

app.get("/manholes", async (req, res) => {
  if (!pool) {
    return res.json({ message: "DB not configured or unavailable", data: [] });
  }

  try {
    const result = await pool.query("SELECT * FROM waste_water_manhole");
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: (err as Error).message || err });
  }
});

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => console.log(`Server running on port ${PORT}`));