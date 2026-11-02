# Development infrastructure (Postgres 16 + MinIO). Production equivalents
# live under infrastructure/{cloud,private,on-premise}/.
#
#   docker compose -f infrastructure/dev/docker-compose.yml --env-file .env up -d
#
# Required env (see .env.example): POSTGRES_DB/USER/PASSWORD.
# The app role password default in postgres-init.sql MUST be changed via
# .env for any shared environment; ops ensure-app-role rotates it.
