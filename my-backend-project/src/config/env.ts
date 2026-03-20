import { config } from 'dotenv';

config();

export const DATABASE_URL = process.env.DATABASE_URL || '';
export const SECRET_KEY = process.env.SECRET_KEY || '';
export const ALLOWED_ORIGINS = process.env.ALLOWED_ORIGINS ? process.env.ALLOWED_ORIGINS.split(',') : [];