// Set in .env (see .env.example). EXPO_PUBLIC_* values are bundled into the app: never put secrets here.
export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000';
export const SUPABASE_URL = process.env.EXPO_PUBLIC_SUPABASE_URL ?? '';
export const SUPABASE_ANON_KEY = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY ?? '';
