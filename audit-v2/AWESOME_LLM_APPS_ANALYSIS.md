# تحلیل معماری Awesome LLM Apps در برابر نقشه‌راه MVP مولتiai

**تاریخ بررسی:** 2026-07-16  
**مخزن بررسی‌شده:** `/tmp/awesome-llm-apps`، commit `6ce858fdce51087a231b07ca423be39020b964ad`  
**مبنای مقایسه:** `/root/multiai/audit-v2/S9_MVP_ROADMAP.md` و کد فعلی Multiai  
**دامنه:** فقط تحلیل و پیشنهاد؛ هیچ کد محصولی در Multiai تغییر نکرده است.

## خلاصه اجرایی

Awesome LLM Apps یک مخزن آموزشی/نمونه‌ای است، نه یک معماری آمادهٔ production. ارزش اصلی آن برای Multiai در **الگوها** است: memory retrieval با شناسهٔ کاربر، UI ابزارمحور با schema محدود، وضعیت مشترک agent/UI، pipeline پژوهش مرحله‌ای، و اصول RAG مثل scope/filter و citation. در مقابل، کدها غالباً Streamlit، وابسته به کلیدهای شخصی، بدون multi-tenancy، کنترل هزینه و threat model کافی هستند و نباید مستقیماً کپی شوند.

**تصمیم اصلی:** تا زمان عبور از گیت Phase 1، هیچ‌یک از Gen UI، MCP، Deep Research یا RAG وارد مسیر اصلی chat نشود. در Phase 2 فقط الگوی schema/renderer برای UI محدود و memory panel قابل استفاده است. در Phase 3، Model Compare و web-search citations مقدم‌اند؛ RAG، research و MCP به‌صورت قابلیت‌های جدا و gated اضافه شوند.

## وضعیت و شواهد بررسی

| موضوع | مرجع واقعی در مخزن | مشاهده | نتیجه برای Multiai |
|---|---|---|---|
| Multi-LLM memory | `advanced_llm_apps/llm_apps_with_memory_tutorials/multi_llm_memory/multi_llm_memory.py:16-27,50-58,78-89` | Mem0+Qdrant، جست‌وجوی memory بر اساس `user_id` و افزودن answer | الگوی مفهومی خوب؛ پیاده‌سازی ناامن/غیرقابل اتکا برای محصول |
| Generative UI / dashboard canvas | `generative_ui_agents/ai-dashboard-canvas-agent/README.md:7-9,56-61` | Canvas پایدار با chart/KPI و chat باریک؛ CopilotKit/AG-UI/ADK | ایدهٔ differentiation قوی، اما stack جدا و خارج از MVP chat |
| Generative UI starter | `generative_ui_agents/generative-ui-starter-project/README.md:1-5,63-119` و `src/hooks/use-generative-ui-examples.tsx:22-81` | state مشترک agent/UI، catalog تایپ‌شده، fixed/dynamic schema، HITL و renderer محدود | schema و HITL قابل اقتباس؛ dynamic UI را فعلاً رد کنیم |
| Deep research | `advanced_ai_agents/single_agent_apps/ai_deep_research_agent/deep_research_openai.py:49-86,89-105,126-181`؛ همچنین `generative_ui_agents/ai-deep-research-agent/src/types/research.ts:9-39` | ابزار Firecrawl با depth/time/url limit، سپس research و elaboration؛ state شامل todo/files/sources | orchestration و source state مفید؛ هزینه/latency/اعتماد به سرویس خارجی بالا |
| RAG | `rag_tutorials/rag-as-a-service/rag_app.py:21-79,99-109`؛ نمونه‌های مکمل `rag_failure_diagnostics_clinic`, `knowledge_graph_rag_citations`, `corrective_rag` | upload از URL، retrieval با `scope`، chunk injection و fallback «نتیجه‌ای نیست» | scope/filter، citation و ارزیابی failure قابل استفاده؛ این نمونهٔ ساده production-ready نیست |
| MCP agents | `mcp_ai_agents/multi_mcp_agent/multi_mcp_agent.py:47-67,71-133`؛ config در `mcp_ai_agents/browser_mcp_agent/mcp_agent.config.yaml:11-30` | اجرای چند server با `npx`، انتقال env، ابزارهای GitHub/Perplexity/Calendar؛ logging و secrets جدا | adapter و allowlist لازم است؛ اجرای arbitrary server و OAuth در MVP ممنوع |
| Token/context optimization | جست‌وجوی مخزن الگوهای `token`, `truncate`, `compress`, `summar`, `context`؛ `multi_llm_memory` خطوط 50-58 و MCP خطوط 129-132 | الگوی عمومی محدود: retrieval قبل از prompt و `num_history_runs=10`؛ implementation واحد و قابل اتکا برای budget پیدا نشد | از ادعاهای optimization کپی نشود؛ budget واقعی Multiai باید server-side طراحی و اندازه‌گیری شود |

## ارزیابی الگوها: قابل استفاده، مشروط، غیرقابل استفاده

### 1) Memory چندمدلی

**قابل استفاده:**
- memory باید به هویت authenticated کاربر/tenant وصل شود، نه نامی که کاربر در فرم وارد می‌کند (`multi_llm_memory.py:29`).
- قبل از inference، retrieval محدود و مرتبط انجام شود (`:50-58`) و پس از پاسخ، memory candidate ثبت شود (`:78`).
- یک interface مستقل از provider برای `search/add/list/delete` بسازیم تا همه مدل‌ها حافظهٔ یکسان داشته باشند.

**رد یا اصلاح الزامی:**
- `Memory.from_config` و Qdrant localhost (`:16-27`) بدون auth، tenant isolation، encryption، retention و timeout است.
- `full_prompt` متن memory را خام داخل prompt می‌گذارد (`:58`)؛ با یافتهٔ S9 دربارهٔ injection/cap ناسازگار است.
- `memory.add(answer)` همهٔ پاسخ را ذخیره می‌کند؛ PII، secrets و prompt injection می‌تواند ماندگار شود.
- انتخاب Claude در نمونه به‌طور مشکوک `Memory.from_config` را به‌عنوان client استفاده می‌کند (`:35-45`)؛ این نمونه benchmark معماری نیست.

**تصمیم:** P2.7 فقط UI و قرارداد sanitized memory؛ P3.2 استخراج خودکار پس از consent، با همان caps S9 (`MAX_SOUL_CHARS=2000`, `MAX_MEM_CHAR=500`, `MAX_MEM_COUNT=5`) و review/delete کاربر.

### 2) Generative UI، dashboard canvas و starter

**قابل استفاده:**
- ایدهٔ canvas به‌عنوان surface پایدار و artifactهای addressable (`ai-dashboard.../README.md:7-9`) برای Phase 3 عالی است.
- catalog تعریف‌شده با Zod و rendererهای مشخص (`generative-ui-starter.../README.md:95-119`) به‌جای HTML/JS تولیدی خام.
- HITL برای عملیات حساس (`useHumanInTheLoop` در `use-generative-ui-examples.tsx:27-40`) و renderer پیش‌فرض ابزار (`:57-68`).
- fixed schema که فقط data تغییر می‌کند (`README.md:101-108`) امن‌تر از dynamic schema است.

**غیرقابل استفاده در حال حاضر:**
- انتقال CopilotKit/AG-UI/ADK/LangGraph به FastAPI/Next.js فعلی، سطح پیچیدگی، dependency و observability جدید می‌سازد.
- dynamic A2UI (`README.md:104-108`) سطح حمله و ریسک XSS/فیشینگ دارد؛ هیچ component یا URL خارج از catalog نباید render شود.
- canvas برای chat scope فعلی و گیت Phase 2 ضرورتی ندارد.

**تصمیم:** P2 یک «tool card» و renderer محدود با Zod/JSON Schema، بدون اجرای کد و بدون HTML خام. Canvas dashboard فقط P3، بعد از Model Compare و با allowlist componentها.

### 3) Deep Research

**قابل استفاده:**
- پارامترهای صریح depth/time/max URLs (`deep_research_openai.py:51-64`) برای budget و timeout.
- تفکیک research اولیه از elaboration (`:126-152`) برای pipeline قابل مشاهده.
- مدل state برای `todos`, `files`, `sources` و status (`research.ts:9-39`) برای progress UI و citation مناسب است.

**رد/اصلاح:**
- کلیدها در sidebar/session state نگه‌داری می‌شوند (`:17-40`)؛ Multiai باید secret server-side باشد.
- `except Exception` و نمایش خطای خام (`:84-86,180-181`) با S9/B5 ناسازگار است.
- سرویس Firecrawl و اجرای 3 دقیقه/10 URL (`:91-102`) هزینه و latency نامحدود ایجاد می‌کند؛ باید quota، cancellation، SSRF policy، robots/terms و cache داشته باشد.
- «elaboration» بدون verification می‌تواند hallucination را بیشتر کند؛ citation باید به claim/منبع وصل و قابل مشاهده باشد.

**تصمیم:** P3.5 ابتدا web-search API ساده با citation و provenance؛ Deep Research کامل فقط experiment جدا، با سقف سخت هزینه/زمان و خروجی async.

### 4) RAG

**قابل استفاده:**
- `scope` در retrieval (`rag_app.py:47-73`) الگوی خوبی برای tenant/workspace/document ACL است.
- pipeline شفاف retrieve → prompt → generate (`:99-109`) و fallback بدون نتیجه (`:105-106`).
- نمونه‌های `knowledge_graph_rag_citations`, `rag_failure_diagnostics_clinic`, `corrective_rag` برای citation، failure taxonomy و اصلاح retrieval ارزش مطالعه دارند.

**رد/اصلاح:**
- upload مستقیم URL (`:21-45`) SSRF، دانلود فایل بزرگ، MIME spoof و محتوای مخرب را باز می‌کند.
- timeout، retry/backoff، size limit، content validation و ACL در این نمونه دیده نمی‌شود.
- chunkها بدون provenance/score در prompt گذاشته می‌شوند (`:75-79`) و prompt injection داخل سند می‌تواند دستور شود.
- کلیدهای API در UI (`:126-143`) و `time.sleep(5)` (`:164`) برای production نامناسب‌اند.

**تصمیم:** RAG در P3 به‌صورت workspace documents با ingestion queue، object scanning، ACL، chunk budget، source IDs و citation؛ vector DB را از memory جدا نگه داریم مگر نیاز عملی ثابت شود.

### 5) MCP agents

**قابل استفاده:**
- MultiMCP یک abstraction برای اتصال چند ابزار و lifecycle (`multi_mcp_agent.py:56-67`) نشان می‌دهد.
- secrets جدا از config (`browser_mcp_agent/mcp_agent.config.yaml:18-30`) و logging قابل trace (`:1-9`) ایده‌های درست‌اند.
- MCP را به‌عنوان capability adapter پشت policy engine می‌توان به catalog ابزارهای Multiai تبدیل کرد.

**ریسک/رد:**
- `npx -y` و packageهای `@latest` (`multi_mcp_agent.py:56-60`, config `:13-16`) supply-chain خطرناک و non-reproducible هستند.
- انتقال `os.environ` (`:49-54`) اصل least privilege را نقض می‌کند؛ GitHub/Gmail/Calendar دادهٔ حساس و side effect دارند.
- دستورهای agent برای «create/update/merge» (`:87-93`) بدون confirmation، scope و audit مناسب نیستند.

**تصمیم:** MCP فقط P3 و ابتدا read-only، package pin شده، sandbox/egress allowlist، per-tenant credentials، schema validation، timeout، rate/cost limit، audit log و HITL برای هر write/delete/send.

### 6) Token optimization و context budget

در بررسی فعلی، مخزن یک implementation مرجع و جامع برای token optimization پیدا نکرد؛ موارد قابل مشاهده بیشتر **retrieval محدود** (`multi_llm_memory.py:50-58`) و **history cap** (`multi_mcp_agent.py:129-132`) هستند. بنابراین این مخزن مدرک کافی برای افزودن tokenizer، compression یا summarization به Multiai نیست.

**پیشنهاد مستقل برای Multiai:**
1. قبل از upstream، budget سخت بر اساس context مدل: system + memory + history + user + reserve output.
2. history را با token count واقعی trim و سپس summary versioned تولید کن؛ summary را fact قطعی تلقی نکن.
3. memory retrieval با top-k و سقف کاراکتر/توکن و dedup.
4. برای هر درخواست metrics: input/output tokens، rejected/truncated context، latency و cost.
5. هر تغییر optimization با golden set فارسی/انگلیسی و regression روی billing آزموده شود.

## امنیت، حریم خصوصی و licensing

### ریسک‌های فنی
- API key در UI/session state در چند نمونه (`multi_llm_memory.py:10-14`; `rag_app.py:126-143`; deep research `:17-40`) نباید وارد Multiai شود.
- user ID دستی (`multi_llm_memory.py:29`) قابل جعل و نقض isolation است.
- memory و اسناد ورودی untrusted هستند؛ باید data/instruction separation، escaping و marker sanitization اجرا شود.
- URL ingestion خطر SSRF دارد؛ فقط HTTPS، DNS/IP denylist، redirect policy، timeout و محدودیت اندازه لازم است.
- MCP با latest package، env گسترده و write tools ریسک supply chain، credential exfiltration و side effect دارد.
- debug/logging (`multi_mcp_agent.py:126-129`) ممکن است prompt، شناسه و دادهٔ شخصی را ثبت کند؛ redaction الزامی است.
- استقرار سرویس‌های خارجی (OpenAI/Anthropic/Ragie/Firecrawl/Perplexity/Google) با قیود ایران، انتقال داده، SLA و هزینه سازگار نیست مگر provider policy و مسیر شبکه بررسی شود.

### مجوز
- مجوز ریشهٔ مخزن Apache-2.0 است (`/tmp/awesome-llm-apps/LICENSE`)، اما مجوز هر زیرپروژه یکسان نیست.
- `ai-dashboard-canvas-agent/LICENSE` MIT است (`:1-21`).
- پیش از کپی substantial، NOTICE/copyright و تغییرات باید حفظ شوند؛ Apache-2.0 بخش‌های patent و notice دارد.
- dependencyها و SDKها مجوز مستقل دارند؛ `npm/pnpm`, Python و MCP serverهای بیرونی باید با SBOM/license scan بررسی شوند.
- «نمونهٔ مخزن» مجوز API/provider یا حق استفاده از دادهٔ GitHub/Google/Gmail/Firecrawl را تضمین نمی‌کند. کپی کد با attribution و ثبت provenance انجام شود، نه کپی کور.

## تصمیم‌های اولویت‌دار ادغام

| اولویت | تصمیم | دلیل/شرط پذیرش |
|---:|---|---|
| P0 | هیچ ادغام featureای قبل از گیت S9 Phase 1 | billing، disconnect، whitelist مدل، memory injection و logging هنوز blocker هستند |
| P1 | استخراج قرارداد memory محدود و UI مدیریت آن | هم‌راستا با P2.7؛ فقط authenticated user، caps، sanitize، delete و audit |
| P1 | تکمیل Markdown/tool rendering محدود | از الگوی catalog/renderer استفاده شود؛ خروجی مدل هرگز arbitrary JSX/HTML اجرا نکند |
| P2 | Model Compare پیش از canvas/research/MCP | moat اعلام‌شدهٔ S9 با کمترین dependency جدید؛ reuse همان billing/streaming |
| P2 | Web search با citation و provenance | هستهٔ P3.5؛ ابتدا provider abstraction، cache، SSRF و cost cap |
| P3 | RAG workspace | پس از ACL و storage؛ scope/filter و citation از نمونه‌ها اقتباس شود |
| P3 | Deep Research async | پس از search؛ سقف depth/time/URLs، cancellation و budget اجباری |
| P4 | MCP read-only pilot | allowlist و pin؛ writeها فقط HITL و audit؛ خارج از chat hot path |
| P5 | Canvas/Gen UI | یک catalog کوچک ثابت، بعد از اثبات نیاز کاربر؛ dynamic schema فعلاً ممنوع |

## نقشه‌راه به‌روزشده Phase 1/2/3

### Phase 1 — Stabilize (بدون تغییر موضوع)
- تمام P1.1 تا P1.10 سند S9 حفظ شوند.
- یک **context-budget test** به exit gate اضافه شود: memory/history بزرگ truncate/summarize کنترل‌شده، هزینهٔ واقعی با ledger سازگار.
- برای هر قابلیت آینده، قرارداد امنیتی و cost budget قبل از implementation نوشته شود.
- معیار exit همچنان live chat، concurrent billing، abort billing، unknown model=400، logs و zero bare exceptهای حساس است.

### Phase 2 — Polish + safe primitives
- P2.1 تا P2.10 طبق S9 اجرا شوند.
- از Generative UI فقط `tool card`, typed catalog و HITL primitive اقتباس شود؛ no A2UI dynamic، no canvas.
- Memory UI به‌جای افزودن provider جدید، روی `context_injection` موجود و قرارداد cap/sanitize سوار شود.
- خروجی Phase 2: chat production-grade، قابل تست browser، بدون تغییر در معماری provider یا اضافه‌کردن agent framework.

### Phase 3 — Differentiate، با ترتیب اصلاح‌شده
1. **Model Compare** (اولویت اول و gate اصلی).
2. **Realtime cost + observability** هم‌زمان با compare، چون دو مدل هزینه و failure بیشتری دارند.
3. **Prompt Library و Auto-Memory** با consent/caps.
4. **Web Search + citations** به‌عنوان پایهٔ RAG و Deep Research.
5. **RAG workspace** با ACL و ingestion امن.
6. **Deep Research async** روی search/RAG، نه قبل از آن.
7. **MCP read-only pilot** و سپس write با HITL.
8. **Dashboard Canvas/Gen UI** آخرین گزینه، فقط با metrics استفاده و catalog ثابت.

**گیت Phase 3:** compare و billing/observability pass؛ سپس هر capability agentی جداگانه feature-flag، budget و kill switch داشته باشد. «AI Agent Platform» بودن نباید به‌معنای عبور از hard gate یا واردکردن frameworkهای نمونه‌ای به chat monolith باشد.

## جمع‌بندی نهایی

Awesome LLM Apps برای Multiai **کتابخانهٔ الگو و منبع طراحی** است، نه dependency معماری. بیشترین ROI فوری از memory contract امن، typed tool rendering، source state/citations و budget parameters می‌آید. بیشترین ریسک از API keyهای client-side، memory خام، URL ingestion، MCP با `npx @latest` و dynamic UI است. توصیهٔ نهایی با S9 هم‌جهت است: **stabilize → polish → differentiate**؛ فقط primitives کم‌خطر Gen UI و context budget به Phase 1/2 اضافه شوند و Deep Research/RAG/MCP/Canvas به بعد از Model Compare و observability موکول گردند.

---

## لاگ راستی‌آزمایی

- فایل‌های مرجع بالا با ابزار خوانده شدند؛ مسیرها و line referenceها بر اساس خروجی واقعی فایل‌ها ثبت شده‌اند.
- commit مخزن Awesome با `git -C /tmp/awesome-llm-apps log -1` بررسی شد.
- وضعیت Multiai با `git -C /root/multiai status --short` بررسی شد؛ پیش از این گزارش، فایل `AWESOME_LLM_APPS_ANALYSIS.md` وجود نداشت و کد محصول برای این کار تغییر نکرد.
- این گزارش ادعای اجرای نمونه‌ها یا اتصال APIهای خارجی ندارد؛ dependencies/کلیدها در محیط حاضر برای چنین ادعایی فراهم و اجرا نشدند.
