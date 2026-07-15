-- Add USD pricing columns to model_catalog for dynamic pricing
ALTER TABLE model_catalog ADD COLUMN IF NOT EXISTS usd_input_per_million DOUBLE PRECISION DEFAULT 0;
ALTER TABLE model_catalog ADD COLUMN IF NOT EXISTS usd_output_per_million DOUBLE PRECISION DEFAULT 0;
