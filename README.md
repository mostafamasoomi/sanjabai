<div align="center">

# 🤖 Sanjhubai

### پلتفرم هوش مصنوعی فارسی | Persian AI Agent Platform

**دسترسی به بهترین مدلهای هوش مصنوعی جهان — با API فارسی، قیمتگذاری شفاف و پشتیبانی محلی**

[![Docker](https://img.shields.io/badge/Docker-Compose-blue?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-15-black?logo=next.js&logoColor=white)](https://nextjs.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-red?logo=redis&logoColor=white)](https://redis.io/)
[![License](https://img.shields.io/badge/License-Proprietary-orange)](#)

---

</div>

## 🌟 چرا Sanjhubai؟

Sanjhubai یک **پلتفرم جامع هوش مصنوعی** است که به کاربران فارسی‌زبان امکان دسترسی به مدل‌های پیشرفته AI را فراهم می‌کند. برخلاف سرویس‌های ساده API gateway، Sanjhubai یک **AI Agent Platform** کامل است با قابلیت‌های مدیریت مکالمه، دستیار شخصی، حافظه بلندمدت، و سیستم billing حرفه‌ای.

<div align="center">

```
┌─────────────────────────────────────────────────────────────────┐
│                    🖥️  Frontend (Next.js 15)                    │
│   RTL Persian UI • Dark/Light Mode • Responsive • 29 Pages     │
├─────────────────────────────────────────────────────────────────┤
│                    ⚡ API Gateway (FastAPI)                      │
│   150 Endpoints • Rate Limiting • Auth • Billing • Streaming   │
├─────────────────────────────────────────────────────────────────┤
│                    🧠 AI Models (Bynara)                        │
│   8 Models • Streaming • Smart Routing • Web Search            │
├─────────────────────────────────────────────────────────────────┤
│              🐘 PostgreSQL  │  🔴 Redis  │  💰 Billing          │
│              31 Tables      │  Sessions  │  Wallet/Reserve      │
└─────────────────────────────────────────────────────────────────┘
```

</div>

## 🚀 ویژگی‌های کلیدی

### 🤖 مدل‌های هوش مصنوعی
| مدل | ارائه‌دهنده | Context | قابلیت‌ها |
|-----|-----------|---------|----------|
| Tencent Hy3 | Bynara | 1M tokens | Chat, Reasoning |
| MiMo V2.5 Pro | Bynara (Xiaomi) | 1M tokens | Chat, Reasoning |
| MiMo V2.5 Pro Ultraspeed | Bynara (Xiaomi) | 1M tokens | Chat, Reasoning |
| DeepSeek V4 Pro | Bynara | 131K tokens | Chat, Reasoning |
| DeepSeek V4 Flash Bynara | Bynara | 131K tokens | Chat |
| DeepSeek V4 Pro Bynara | Bynara | 131K tokens | Chat, Reasoning |
| Mistral Large | Bynara | 252K tokens | Chat, Function Calling |
| Mistral Medium 3.5 (`mistral-medium-3-5`) | Bynara | 256K tokens | Chat, Reasoning, FC |

### 💬 چت و مکالمه
- **Streaming پاسخ** — پاسخ لحظه‌ای با SSE
- **Smart Mode** — مسیریابی هوشمند بین مدل‌ها
- **Web Search** — جستجوی زنده اینترنت با DuckDuckGo
- **File Upload** — ارسال فایل و تحلیل محتوا
- **Model Compare** — مقایسه همزمان چند مدل
- **Markdown Renderer** — رندر کامل Markdown با syntax highlighting

### 🧠 حافظه و دستیار
- **User Memory** — حافظه بلندمدت (ذخیره خودکار + دستی)
- **Assistants** — دستیارهای شخصیسازیشده با system prompt
- **Skills** — قالبهای آماده پرامپت
- **Tasks** — تسکهای زمانبندیشده

### 📄 تولید سند و ارائه (Document Generator)
با یک پرامپت ساده، Sanjhubai به‌صورت خودکار **اسلاید، گزارش و ارائه** حرفه‌ای می‌سازد — بدون نیاز به قالب یا طراحی دستی:

| خروجی | پسوند | کتابخانه | کاربرد |
|-------|-------|----------|--------|
| PowerPoint | `.pptx` | `python-pptx` | ارائه ۱۶:۹ (عنوان، bullet، speaker notes، اسلاید پایانی) |
| Word | `.docx` | `python-docx` | سند ساختاریافته با سرفصل/زیربخش و فوتر برند |
| Markdown Deck | `.md` | built-in | سازگار با Marp / reveal.js برای HTML/PDF |

- **بله — Sanjhubai می‌تواند پاورپوینت، ورد و اسلاید بسازد** (API + UI «سندساز»).
- مدل پیش‌فرض تولید محتوا: `mimo-v2.5-pro` (allow-list مدل‌های Bynara).
- فایل‌ها روی volume `sanjhubai_docs` (`/tmp/sanjhubai_docs`)؛ metadata رجیستری فعلاً in-memory (تا restart API).
- UI: مسیر `/documents` در منوی «سندساز».
- Auth الزامی است (Bearer/session).

```bash
# نیاز به توکن لاگین دارد
TOKEN=$(curl -s -X POST http://localhost:8081/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"..."}' | jq -r .token)

curl -X POST http://localhost:8081/v1/documents/generate \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"prompt":"یک ارائه درباره مزایای هوش مصنوعی در کشاورزی","type":"pptx"}'
# → { "id":"...", "download_url":"/v1/documents/<id>/download", "slides_count":8, ... }
```

> ⚠️ رجیستری اسناد درون‌حافظه‌ای است؛ برای multi-worker/production پایدار → PostgreSQL + Object Storage (نگاه به Roadmap).

### 📚 RAG (بازیابی دانش)
- آپلود سند و chunk/embedding روی PostgreSQL + pgvector
- Query معنایی روی اسناد کاربر
- Endpoints: `POST /v1/rag/upload` · `POST /v1/rag/query` · `GET/DELETE /v1/rag/documents`

### 💱 نرخ دلار لحظه‌ای (tgju)
- `GET /api/exchange-rate` و `GET /exchange-rate` (سازگار با rewrite فرانت `/api/*`)
- منبع اصلی: **tgju.org** (دلار آزاد) با cache Redis و fallback
- تیکر «دلار آزاد» در صفحه اصلی پنل

### 🌐 Proxy / Egress پروایدرها
- ترافیک مدل‌های Bynara از **backhaul HTTP proxy** (`HTTP(S)_PROXY` → `10.10.11.2:8888`) عبور می‌کند
- `NO_PROXY` سرویس‌های داخلی Docker را مستقیم نگه می‌دارد
- تونل SOCKS (`sanjhubai_tunnel:9090`) برای web-search/آینده؛ اگر SSH jump down باشد، LiteLLM روی backhaul می‌ماند

### 💰 سیستم Billing
- **Wallet** — کیف پول با شارژ ریالی
- **Reservation Pattern** — رزرو مبلغ قبل از inference + settlement
- **Idempotent Operations** — جلوگیری از پرداخت مضاعف
- **Credit Packages** — بسته‌های اعتباری
- **Subscriptions** — اشتراک ماهانه
- **Zarinpal Gateway** — درگاه پرداخت ایرانی
- **Usage** — `GET /me/usage` (فرانت: `/api/me/usage`)

### 🔐 امنیت
- **Session Management** — Redis-backed با TTL و rotation
- **Admin Panel** — پنل مدیریت جداگانه با CSRF protection
- **Rate Limiting** — محدودیت درخواست سه‌سطحی (Free/Pro/Enterprise)
- **API Keys** — کلیدهای API با SHA256 + pepper hashing
- **Security Headers** — HSTS, CSP, X-Frame-Options, Permissions-Policy
- **Input Validation** — محافظت در برابر XSS, SQL Injection, CSRF
- **OpenAPI** — `/docs` و `/openapi.json` در production مخفی (404)

### 📊 مدیریت و نظارت
- **Admin Dashboard** — آمار کاربران، درآمد، مصرف
- **User Management** — مدیریت کاربران، ban، ویرایش
- **Analytics** — نمودار مصرف و درآمد
- **Export** — خروجی CSV کاربران و تراکنش‌ها
- **Audit Logging** — ثبت تمام عملیات حساس

## 🛠️ Tech Stack

| لایه | تکنولوژی |
|------|----------|
| **Frontend** | Next.js 15, React 18, TypeScript, Tailwind CSS |
| **Backend** | FastAPI, Uvicorn, Python 3.11 |
| **Database** | PostgreSQL 16, SQLAlchemy (async), pgvector |
| **Cache** | Redis 7 (sessions, rate limits, locks, FX cache) |
| **AI Gateway** | Bynara via self-hosted LiteLLM + HTTP backhaul proxy |
| **Docs** | python-pptx, python-docx |
| **Container** | Docker Compose |
| **Auth** | PBKDF2-SHA256, Session tokens, CSRF |

## 📦 نصب و راه‌اندازی

### پیش‌نیازها
- Docker & Docker Compose
- حداقل 2GB RAM
- API key از Bynara

### Quick Start

```bash
# 1. Clone
git clone https://github.com/mostafamasoomi/sanjabai.git
cd sanjabai

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys

# 3. Start all services
docker compose -f docker-compose.sanjhubai.yml up -d

# 4. Access
# Frontend: http://localhost:3003
# API:      http://localhost:8081
# Health:   http://localhost:8081/health
```

### Environment Variables

```env
# Required
BYNARA_API_KEY=your-bynara-key
API_KEY_PEPPER=your-random-pepper-string
ADMIN_TOKEN=your-admin-token

# Database
POSTGRES_USER=sanjhubai
POSTGRES_PASSWORD=your-db-password
POSTGRES_DB=sanjhubai

# Redis
REDIS_URL=redis://localhost:6379

# Optional
SMTP_HOST=smtp.example.com
SMTP_USER=noreply@yourdomain.com
SMTP_PASS=your-smtp-password
```

## 📁 ساختار پروژه

```
sanjhubai/
├── backend/
│   ├── app.py              # FastAPI application entry
│   ├── auth.py             # Authentication endpoints
│   ├── chat.py             # Chat/completion endpoints
│   ├── admin.py            # Admin panel endpoints
│   ├── wallet.py           # Wallet & billing
│   ├── conversations.py    # Conversation management
│   ├── memory.py           # User memory system
│   ├── assistants.py       # AI assistants
│   ├── skills.py           # Skill templates
│   ├── tasks.py            # Scheduled tasks
│   ├── rag_endpoints.py    # RAG document management
│   ├── api_keys.py         # API key management
│   ├── content.py          # Public content & catalog
│   ├── pricing.py          # Plans & subscriptions
│   ├── notifications.py    # Notification system
│   ├── health.py           # Health check endpoints
│   ├── security.py         # Rate limiting & security
│   ├── dependencies.py     # Auth & session management
│   ├── models.py           # SQLAlchemy models (30 tables)
│   ├── database.py         # DB connection & Redis
│   ├── services/
│   │   ├── billing.py      # Billing service & wallet
│   │   ├── reservation.py  # Reservation primitives
│   │   ├── money.py        # Money value object
│   │   └── memory_extractor.py  # Auto memory extraction
│   ├── middleware/
│   │   ├── security.py     # Security headers
│   │   └── compression.py  # Response compression
│   ├── migrations/         # SQL migrations
│   └── tests/              # Test suite
├── frontend/
│   ├── app/
│   │   ├── chat/           # Chat interface
│   │   ├── admin/          # Admin panel
│   │   ├── models/         # Model catalog
│   │   ├── wallet/         # Wallet management
│   │   ├── pricing/        # Plans & pricing
│   │   ├── assistants/     # AI assistants
│   │   ├── skills/         # Skill templates
│   │   ├── memory/         # Memory management
│   │   ├── tasks/          # Task scheduler
│   │   ├── api-keys/       # API key management
│   │   ├── usage/          # Usage analytics
│   │   ├── compare/        # Model comparison
│   │   ├── playground/     # API playground
│   │   └── documents/      # Document Generator (سندساز)
│   └── components/         # Shared components
├── docker-compose.sanjhubai.yml
└── README.md
```

## 🔌 API Reference

### Public Endpoints (No Auth)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/models` | لیست مدلهای فعال |
| GET | `/catalog/models` | کاتالوگ مدلها |
| GET | `/catalog/pricing` | قیمتگذاری |
| GET | `/plans` | پلنهای اشتراک |
| GET | `/credit-packages` | بستههای اعتباری |
| GET | `/about` | درباره ما |
| GET | `/health` | وضعیت سرویس |
| GET | `/exchange-rate` | نرخ دلار (سازگار با rewrite فرانت) |
| GET | `/api/exchange-rate` | نرخ دلار (مسیر مستقیم) |

### Auth Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/signup` | ثبتنام |
| POST | `/auth/login` | ورود |
| POST | `/auth/logout` | خروج |
| POST | `/auth/forgot-password` | بازیابی رمز |
| GET | `/auth/me` | اطلاعات کاربر |
| PUT | `/auth/profile` | ویرایش پروفایل |

### Chat Endpoints (Auth Required)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/chat/completions` | چت با مدل (streaming) |
| POST | `/v1/smart-chat` | چت هوشمند |
| POST | `/v1/chat/with-file` | چت با فایل |
| POST | `/v1/compare` | مقایسه مدلها |

### Wallet & Billing (Auth Required)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/wallet` | موجودی کیف پول |
| POST | `/wallet/topup` | شارژ کیف پول |
| GET | `/subscription` | وضعیت اشتراک |
| POST | `/subscribe` | خرید اشتراک |
| GET | `/payment/history` | تاریخچه پرداخت |
| GET | `/me/usage` | مصرف و هزینه (فرانت: `/api/me/usage`) |

### Document Generator (Auth Required)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/documents/generate` | تولید سند (نوع: `pptx`/`docx`/`mdx`) از پرامپت |
| GET | `/v1/documents` | لیست اسناد تولیدشده کاربر |
| GET | `/v1/documents/{id}/download` | دانلود سند |
| DELETE | `/v1/documents/{id}` | حذف سند |

### RAG (Auth Required)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/rag/upload` | آپلود سند برای ایندکس |
| POST | `/v1/rag/query` | پرسش معنایی (`question`) |
| GET | `/v1/rag/documents` | لیست اسناد RAG |
| DELETE | `/v1/rag/documents/{id}` | حذف سند |
| GET | `/v1/rag/documents/{id}/status` | وضعیت ایندکس |

> 📖 مستندات کامل API: `http://localhost:8081/docs` (فقط در حالت DEBUG)

## 🔒 امنیت

| لایه | محافظت |
|------|--------|
| **Authentication** | Session tokens (256-bit) + Redis TTL |
| **Authorization** | Admin/User separation + CSRF tokens |
| **Rate Limiting** | Redis sliding window, 3 tiers |
| **Input Validation** | XSS/SQLi/CSRF protection |
| **Transport** | HTTPS via reverse proxy + HSTS |
| **Password** | PBKDF2-SHA256 (100k iterations) |
| **API Keys** | SHA256 + server-side pepper |
| **Headers** | CSP, X-Frame-Options, Permissions-Policy |
| **Session** | HttpOnly, Secure, SameSite=Lax cookies |

## 🗺️ نقشهراه (Roadmap)

- [x] **AI Agent Platform** — چت، حافظه، دستیار، مارکت‌پلیس مدل
- [x] **Document Generator** — تولید خودکار PPTX / DOCX / MDX
- [x] **RAG Core** — upload/query/pgvector
- [x] **Live FX (tgju)** — نرخ دلار آزاد + تیکر هوم
- [x] **Provider backhaul proxy** — egress مدل‌ها از پروکسی
- [ ] **Persistent Document Storage** — انتقال رجیستری درون‌حافظه به PostgreSQL + Object Storage (MinIO/S3)
- [ ] **DocGen Billing** — reserve/settle روی wallet (فعلاً MVP بدون کسر جداگانه)
- [ ] **Templates** — قالب‌های آماده ارائه (کسب‌وکار، آموزشی، فروش)
- [ ] **Image/Chart Embedding** — تزریق نمودار و تصویر در اسلایدها
- [ ] **Multi-language Docs** — تولید سند فارسی/انگلیسی با RTL صحیح در DOCX
- [ ] **Batch & Scheduled Generation** — تولید زمان‌بندی‌شده گزارش‌های دوره‌ای
- [ ] **Usage Metering for Docs** — احتساب هزینه تولید سند روی wallet

## 📊 آمار فنی

| متریک | مقدار |
|-------|-------|
| API Endpoints | 150 |
| Frontend Pages | 29 |
| Database Tables | 31+ |
| SQLAlchemy Models | 30 |
| AI Models (available) | 8 Bynara |
| Document formats | PPTX · DOCX · MD |
| Security baseline | `/docs` hidden, authz on wallet/usage/rag/docs |
| MVP Readiness | ✅ Ready (verified restart + E2E) |

## 🤝 مشارکت

1. Fork کنید
2. Branch بسازید (`git checkout -b feature/amazing`)
3. Commit بزنید (`git commit -m 'Add amazing feature'`)
4. Push کنید (`git push origin feature/amazing`)
5. Pull Request باز کنید

## 📄 License

MIT — see [LICENSE](./LICENSE).

---

<div align="center">

**ساخته شده با ❤️ برای جامعه فارسی‌زبان**

[GitHub](https://github.com/mostafamasoomi/sanjabai) • [sanjhubai.ir](https://sanjhubai.ir)

</div>
