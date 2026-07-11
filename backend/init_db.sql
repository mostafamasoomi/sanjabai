-- Initialize multiai database

-- Pricing
INSERT INTO pricing (model, input_per_million, output_per_million, currency, updated_at) VALUES
('kr/gpt-4o-mini', 2, 6, 'IRT', NOW()),
('kr/claude-3.5-sonnet', 10, 30, 'IRT', NOW()),
('kr/gpt-4o', 15, 45, 'IRT', NOW()),
('kr/llama-3.1-405b', 5, 15, 'IRT', NOW())
ON CONFLICT (model) DO NOTHING;

-- Features
INSERT INTO features (title, description, icon, order_idx, active, updated_at) VALUES
('چت هوشمند', 'دسترسی به جدیدترین مدلهای هوش مصنوعی برای چت و پاسخگویی', '💬', 1, TRUE, NOW()),
('سرعت بالا', 'پاسخگویی در کمتر از ۱ ثانیه با زیرساخت بهینه', '⚡', 2, TRUE, NOW()),
('پشتیبانی فارسی', 'پشتیبانی کامل از زبان فارسی و لهجه‌های مختلف', '🇮🇷', 3, TRUE, NOW()),
('حریم خصوصی', 'عدم ذخیره‌سازی مکالمات و حفظ حریم خصوصی کاربران', '🔒', 4, TRUE, NOW())
ON CONFLICT (title) DO UPDATE SET description = EXCLUDED.description, icon = EXCLUDED.icon, order_idx = EXCLUDED.order_idx, active = EXCLUDED.active, updated_at = EXCLUDED.updated_at;

-- Discounts
INSERT INTO discounts (code, percent, active, updated_at) VALUES
('WELCOME10', 10, TRUE, NOW()),
('SUMMER20', 20, TRUE, NOW())
ON CONFLICT (code) DO UPDATE SET percent = EXCLUDED.percent, active = EXCLUDED.active, updated_at = EXCLUDED.updated_at;

-- About
INSERT INTO about_content (title, body, updated_at) VALUES
('درباره ما', 'ما یک پلتفرم هوش مصنوعی فارسی هستیم که با هدف ارائه بهترین تجربه کاربری و دسترسی به جدیدترین مدلهای هوش مصنوعی ایجاد شده‌ایم. تیم ما متشکل از متخصصان حوزه فناوری و هوش مصنوعی است که با عشق به زبان فارسی و فرهنگ ایرانی، این پلتفرم را توسعه داده‌اند.', NOW())
ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title, body = EXCLUDED.body, updated_at = EXCLUDED.updated_at;

-- Proxy
INSERT INTO proxy_config (proxy_url, proxy_type, active, updated_at) VALUES
('socks5://ted:T%23d%40123234@multiai_tunnel:9090', 'socks5', TRUE, NOW())
ON CONFLICT (id) DO UPDATE SET proxy_url = EXCLUDED.proxy_url, proxy_type = EXCLUDED.proxy_type, active = EXCLUDED.active, updated_at = EXCLUDED.updated_at;