# VeraPlex mobile

Expo (React Native) client for raising deviations with or without a connection.

- `src/core/` – framework-free logic (outbox, sync engine, API client, capture). Unit-tested with `npm test`.
- `src/ui/`, `src/lib/`, `App.tsx` – screens and wiring (Supabase sign-in, NetInfo/AppState sync triggers).
- `e2e/` – `npm run e2e` starts the real FastAPI backend on a throwaway SQLite DB and runs the sync engine against it (lost-response replay, expired token, permission failure).

Configure `.env` from `.env.example` (`EXPO_PUBLIC_*` values are bundled into the app; never put secrets there).
