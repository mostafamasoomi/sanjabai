# Infrastructure Brand Rename: Sanjhubai -> Sanjabai

This runbook outlines the required infrastructure changes to rename the project and services from `sanjhubai` to `sanjabai` cleanly without data loss.

## Overview of Changes

1. **Directories**: `/root/sanjhubai` -> `/root/sanjabai`
2. **Docker Compose Project Name**: `sanjhubai` -> `sanjabai`
3. **Docker Services**: `sanjhubai_pg`, `sanjhubai_redis`, etc. -> `sanjabai_*`
4. **Docker Volumes**: `sanjhubai_pg_data`, `sanjhubai_redis_data` -> `sanjabai_*`
5. **Database Role / DB Name**: `sanjhubai` -> `sanjabai`

## Safe Volume Migration Sequence (Zero Data Loss)

Docker volumes cannot be renamed directly. The volume data must be copied while containers are offline.

### 1. Stop Existing Stack
```bash
cd /root/sanjabai
docker compose -f docker-compose.sanjabai.yml down
```

### 2. Copy Data to New Volumes
```bash
docker volume create sanjabai_pg_data
docker volume create sanjabai_redis_data
docker volume create sanjabai_docs

# Copy Postgres Volume
docker run --rm \
  -v sanjhubai_pg_data:/from -v sanjabai_pg_data:/to \
  alpine sh -c "cp -a /from/. /to/"

# Copy Redis Volume
docker run --rm \
  -v sanjhubai_redis_data:/from -v sanjabai_redis_data:/to \
  alpine sh -c "cp -a /from/. /to/"
```

### 3. Rename Database & User inside Postgres
```bash
docker compose -f docker-compose.sanjabai.yml up -d sanjabai_pg
sleep 10
docker exec -i sanjabai-sanjabai_pg-1 psql -U sanjhubai -d postgres << 'SQL'
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'sanjhubai' AND pid <> pg_backend_pid();
ALTER DATABASE sanjhubai RENAME TO sanjabai;
ALTER ROLE sanjhubai RENAME TO sanjabai;
SQL

# Re-set password for renamed role (since hash is salted with role name)
PW=$(grep -oP '(?<=POSTGRES_PASSWORD=).*' /root/sanjabai/.env)
docker exec -i sanjabai-sanjabai_pg-1 psql -U sanjabai -d postgres -c "ALTER ROLE sanjabai WITH PASSWORD '$PW';"
```

### 4. Rebuild & Start Full Stack
```bash
docker compose -f docker-compose.sanjabai.yml up -d --build
```

## Rollback Plan

If any step fails:
1. Bring down the new stack: `docker compose -f docker-compose.sanjabai.yml down`
2. Start the old stack: `docker compose -f docker-compose.sanjhubai.yml up -d`
3. Verify that old volumes `sanjhubai_pg_data` and `sanjhubai_redis_data` are intact.
