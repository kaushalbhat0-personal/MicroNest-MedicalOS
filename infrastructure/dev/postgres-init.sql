-- Dev database init. Runs once at first volume creation.
-- Creates the least-privilege app role; the password is injected from the
-- environment by compose (POSTGRES_APP_PASSWORD). Production sets this via
-- the secret manager / ops ensure-app-role — never baked into an image.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'hos_app') THEN
    CREATE ROLE hos_app LOGIN PASSWORD 'change-me-app-role';
  END IF;
END
$$;
ALTER DATABASE "healthcare_os" OWNER TO "hos_owner";
