# Exhibition Preflight Phase 2 Notes

## Local Environment

Backend configuration loads local environment files in this order:

- `.env`
- `backend/.env`
- `.env.local`
- `backend/.env.local`
- profile-specific variants when `AEGIS_PROFILE`, `AEGIS_ENV`, or `APP_ENV` is set

These files are ignored by git. Keep real secrets only in backend-loaded local env files. Do not put secrets in `.venv` or in frontend `VITE_` variables.

For LLM/OSINT readiness, use:

```env
OPENAI_API_KEY=
```

The frontend receives only provider readiness booleans and masked metadata from preflight/capability status. It must never receive the raw key.

If a real provider key is pasted into chat or logs, treat it as exposed, rotate it with the provider, and place only the replacement value in the backend local env file.

## Admin Access

Existing local users are never overwritten by bootstrap. If no users exist and `AEGIS_BOOTSTRAP_ADMIN_PASSWORD` is not set in development, the backend creates a local admin and writes the generated password to:

```text
storage/security/bootstrap_admin_password.txt
```

That storage path is ignored by git. The password is not printed in backend logs.

For an intentional local exhibition password, set `AEGIS_BOOTSTRAP_ADMIN_PASSWORD` in the backend-loaded local env file before first startup. If an existing admin needs a reset, use the authenticated admin reset API from the Security page or the explicit `/api/security/users/{user_id}/reset-password` endpoint. The system does not silently delete or rewrite local users.

## Health Layers

- `/health` is process liveness and stays lightweight.
- `/api/system/readiness` verifies API shell, auth/security config, local storage, and registry readiness with lightweight checks.
- `/api/preflight/*` owns exhibition readiness and controlled capability warmup checks.
