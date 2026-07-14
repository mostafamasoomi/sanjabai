-- Add default_model column to proxy_config for org-wide default model setting
ALTER TABLE proxy_config ADD COLUMN IF NOT EXISTS default_model TEXT NOT NULL DEFAULT '';
