# دليل النشر: GitHub + Supabase + Vercel + OpenAI

```
المتصفح ─HTTPS─► Vercel fra1 · FastAPI (src/asgi.py) + web/  (https://manhaj-three.vercel.app)
                   ├─► Supabase eu-central-1 · Postgres + pgvector (transaction pooler :6543)
                   ├─► Supabase Storage · حاوية خاصة "sources": PDF (رابط موقّع 10 دقائق) وصور الصفحات (15 دقيقة)
                   ├─► OpenAI · Responses API ببث الخطوات (DIAGNOSIS_MODEL، store=False، بحث ويب في مواقع محددة)
                   │          + المراجع الناقد (CRITIC_MODEL) + أسئلة المتابعة (FOLLOWUP_MODEL) + embeddings(3-small@768)
                   ├─► api.turath.io · مقتطفات المكتبة الشاملة للألفاظ المقتبسة
                   └─► alquran.cloud + hadith-api (jsDelivr ثم GitHub) · التحقق من الآيات والأحاديث بأرقامها
سطر الأوامر المحلي (إدخال، استخراج آلي، فهرسة كاملة، تكرار/عائلات، صور الصفحات، نسخ احتياطي) ─► Supabase (session pooler :5432)
GitHub (خاص) ─► CI ─► Vercel: main → Production · PR → Preview للقراءة فقط
supabase/migrations/*.sql ─(npx supabase db push أو Supabase MCP، قبل دمج الكود المعتمد عليها)─► Supabase
```

| الأداة | الاستخدام |
|---|---|
| `gh` | إنشاء المستودع، الدفع، طلبات الدمج، حالة CI |
| `npx supabase` | `link`، `migration new`، `db push`، `db dump` |
| Supabase MCP | الجداول، الامتدادات، المستشار الأمني، السجلات، استعلامات قراءة، و`apply_migration` حين يتعذر تشغيل `npx supabase` |
| `npx vercel` | `login`، `link`، `git connect`، `env add`، `deploy` |
| Vercel MCP | حالة النشر، سجلات البناء والتشغيل، ملفات الحزمة، وإنشاء نشر من GitHub إن فات النشرَ التلقائي |

المعرّفات العامة: المستودع `hussain-alayfei/manhaj-objection-dataset` (خاص)، ومشروع Vercel `manhaj` (Hobby، fra1)، ومشروع Supabase بالمرجع `zpzgehdmaexzakukojyw` (eu-central-1). المفاتيح لا تُكتب في المستودع ولا في المحادثات.

## 1. GitHub

```bash
git init -b main
git add -A && git status        # لا PDF ولا .db ولا .env ولا data/* سوى README/.gitkeep
gh repo create hussain-alayfei/manhaj-objection-dataset --private --source . --push
```

بعد ذلك لكل تغيير: فرع ← `gh pr create` ← CI أخضر + معاينة Vercel ← دمج إلى main ← الإنتاج. يُفضَّل الدمج بإعادة الأساس (rebase) حين يلزم أن يبقى كل commit قابلًا للتراجع وحده. لا دفع مباشر إلى main.

## 2. Supabase

أداة MCP لا تُتم إنشاء المشروع (تتطلب تأكيد تكلفة غير متاح فيها)، لذا يُنشأ من سطر الأوامر. من طرفيتك، داخل مجلد المستودع:

```bash
npx supabase login
npx supabase projects create manhaj --org-id ydidykfbqgcswaodxsml --region eu-central-1
npx supabase link --project-ref <ref>
npx supabase db push
npx supabase migration list
```

`projects create` يطلب كلمة مرور قاعدة البيانات: اختر كلمة طويلة من حروف وأرقام فقط (لا تحتاج ترميزًا داخل الرابط) واحفظها في مدير كلمات المرور. ثم من اللوحة انسخ من **Connect** سلسلتي session (`:5432`) وtransaction (`:6543`) كما هما (قد يكون المضيف `aws-1-…`)، والمفتاح **secret** من API Keys. لا تُلصق في المحادثة.

التحقق عبر MCP: 23 جدولًا في `public` (منها `accounts` و`sessions` و`events` من هجرة الحسابات)، امتداد `vector` في `extensions`، الحاوية `sources` خاصة وتقبل `application/pdf` و`image/webp`، وملاحظات `rls_enabled_no_policy` متوقعة (RLS مفعّل بلا سياسات عمدًا؛ التطبيق يتصل بصفته مالك الجداول).

## 3. Vercel

أداة Vercel MCP لا تملك صلاحية إنشاء مشروع في نطاق الحساب، لذا الربط من سطر الأوامر بعد تسجيل الدخول:

```bash
npx vercel@latest login
npx vercel link --yes --project manhaj
npx vercel git connect
```

إن لم يظهر المستودع الخاص، امنح تطبيق Vercel على GitHub صلاحية الوصول إليه.

`vercel.json` يثبت المنطقة `fra1` و`maxDuration: 300` ويستبعد `data/` و`tests/` و`docs/` و`scripts/` و`supabase/` و`work/` من الحزمة، و`pyproject.toml` يحدد `src.asgi:app` ويقدّم `web/` من CDN. صور `/static/img` والخطوط تُخزَّن مؤقتًا بلا انتهاء (immutable)، فالصورة البديلة تأخذ اسم ملف جديدًا دائمًا. نشر تجريبي بلا أسرار حقيقية:

```bash
npx vercel deploy -e DATABASE_URL=sqlite:////tmp/smoke.db -e ALLOW_SQLITE_SMOKE=1 -e REVIEWER_TOKEN_HASHES='{"smoke":"<sha256>"}'
```

## 4. الأسرار (يُدخلها المالك)

رموز التشغيل (للأوامر وواجهة API وصلاحية المسؤول؛ شاشة الدخول في الموقع تقبل الحسابات وحدها). لا تُطبع؛ سلّم كل ملف لصاحبه ثم احذفه:

```bash
python scripts/create_reviewer.py hussain     --env-file .env.production.local --token-out work/token-hussain.txt
python scripts/create_reviewer.py reviewer-02 --env-file .env.production.local --token-out work/token-reviewer-02.txt
python scripts/create_reviewer.py reviewer-03 --env-file .env.production.local --token-out work/token-reviewer-03.txt
```

ثم لكل متغير: `npx vercel env add <NAME> production` (و`preview`):

| المتغير | Production | Preview |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://postgres.<ref>:<pw>@<pooler-host>:6543/postgres` | `sqlite:////tmp/preview.db` مع `ALLOW_SQLITE_SMOKE=1` |
| `READ_ONLY` | لا يُضبط | `1` |
| `REVIEWER_TOKEN_HASHES` | السطر من `.env.production.local` | نفسه |
| `OPENAI_API_KEY` | مفتاح مشروع OpenAI مع حد إنفاق شهري | لا يُضبط |
| `LLM_PROVIDER` / `DIAGNOSIS_MODEL` / `DIAGNOSIS_REASONING_EFFORT` | `openai` / `gpt-6.1-sol` / `low` | `none` |
| `CRITIC_MODEL` / `FOLLOWUP_MODEL` | اختياريان: المراجع الناقد وأسئلة المتابعة على `DIAGNOSIS_MODEL` إن لم يُضبطا | لا يُضبطان |
| `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` / `EMBEDDING_DIM` | `openai` / `text-embedding-3-small` / `768` | نفسه |
| `STORAGE_BACKEND` / `SUPABASE_URL` / `SUPABASE_SECRET_KEY` / `SUPABASE_STORAGE_BUCKET` | `supabase` / رابط المشروع / المفتاح السري / `sources` | `local` (دون المفتاح السري) |
| `DIAGNOSE_DAILY_LIMIT` | `50` (لكل حساب في اليوم) | `10` |
| `DIAGNOSE_GLOBAL_DAILY_LIMIT` | `200` (كل الحسابات معًا، يحمي إنفاق OpenAI) | لا يُضبط |
| `ASK_DAILY_LIMIT` | `60` لكل حساب في اليوم (القيمة الافتراضية إن لم يُضبط؛ `0` بلا حد) | لا يُضبط |
| `SIGNUP_ENABLED` | `1` (أي شخص ينشئ حسابًا ويراجع) | `1` |
| `ADMIN_EMAILS` | بريد مسؤول المشروع، مفصولًا بفواصل | لا يُضبط |
| `PUBLIC_ACCESS` | لا يُضبط (الدخول بحساب) | لا يُضبط |

الحدود اليومية تُحسب باليوم UTC، و`0` يعني بلا حد. لا تُحسب في وضع القراءة فقط.

متغيرات اختيارية بقيمها الافتراضية في الكود: `DIAGNOSIS_MAX_OUTPUT_TOKENS=12000` (يشمل تفكير النموذج)، و`DIAGNOSIS_TIMEOUT=150` ثانية، و`SOURCE_CHECK_TIMEOUT=6` ثوانٍ (التحقق من النصوص والمكتبة الشاملة)، و`READ_CACHE_SECONDS=10`، و`EMBED_REFRESH_LIMIT=400`، و`ENABLE_HEAVY_ENDPOINTS` (مغلق: المهام الثقيلة من سطر الأوامر)، و`ALLOWED_ORIGINS` (نطاق مخصص)، و`LOG_LEVEL=INFO`.

ملف `.env` المحلي يحمل القيم نفسها، لكن `DATABASE_URL` على session pooler `:5432`. **النسخة المحلية من الموقع تعمل للقراءة فقط تلقائيًا** عندما تشير إلى قاعدة بعيدة (الإنتاج)، لأن الاعتماد وسجل التدقيق لا يُحذفان؛ للكتابة المقصودة اضبط `ALLOW_REMOTE_WRITES=1` مؤقتًا. أوامر سطر الأوامر (`seed_book.py` و`upload_source_pdf.py` و`render_source_pages.py` و`src.cli`) تكتب عمدًا، فشغّلها فقط وأنت تقصد الإنتاج.

**نسخ المعاينة (Preview):** تعمل على قاعدة SQLite مؤقتة فارغة دون مفاتيح الإنتاج، فلا يستطيع أي فرع تجريبي الكتابة في قاعدة الإنتاج أو الصرف من OpenAI. ولأن إنشاء الحساب كتابة، فلا تُختبر الصفحات الداخلية على المعاينة؛ تُختبر الواجهة بنسخة ثابتة مع بيانات وهمية (انظر [AGENTS.md](../AGENTS.md)).

## 5. بذر قاعدة Supabase (محليًا)

```bash
mkdir -p work && cp data/source/SRC-e209f0cca8a26244/original.pdf work/book.pdf   # لا تمرر المسار الأصلي (SameFileError)
python scripts/seed_book.py work/book.pdf
python scripts/verify_dataset.py
python scripts/upload_source_pdf.py SRC-e209f0cca8a26244
python scripts/render_source_pages.py SRC-e209f0cca8a26244   # صور الصفحات لعارض الكتاب داخل الموقع
python -m src.cli embeddings --include-drafts
```

المتوقع: 253 مقطعًا، 103 شبهات، 14 قاعدة، 240 إصدارًا، و152 صورة صفحة. سجلات التدقيق غير قابلة للحذف؛ إعادة التشغيل آمنة (idempotent)، أما التصفير الكامل `npx supabase db reset --linked` فمدمّر ويحتاج قرار المالك.

## 6. التحقق بعد النشر

- يوجد نشر إنتاجي لـcommit الدمج نفسه. إن لم يظهر (فات Vercel إشعار الدفع إلى main أحيانًا)، أنشئ نشرًا من مصدر GitHub (`main` مع sha الـcommit) عبر Vercel MCP.
- `/health` = 200، والصفحة العامة تظهر، والدخول بحساب قائم يعمل. لا تنشئ حسابات تجريبية في الإنتاج.
- النظرة العامة تعرض 103 شبهات و14 قاعدة.
- فتح PDF من المصادر (رابط موقّع في نافذة جديدة)، وعارض الكتاب يعرض الصفحات.
- تحليل «بكل قواعد الكتاب» يعرض الخطوات الإحدى عشرة وهي تُكتب، موسومًا «مسودة» مع الصفحات؛ والوضع المعتمد يمتنع (`no_approved_methodology`) حتى تُعتمد قواعد. التحليل يُحفظ في سجل صاحبه ويمكن حذفه منه.
- لا تجرِ اعتمادات تجريبية في الإنتاج؛ اختبارات الكتابة تُجرى على نسخة SQLite محلية (`DATABASE_URL=sqlite:///work/test.db`).
- المعاينة: القراءة تعمل والكتابة 403.

## العمل المستمر

- **قاعدة البيانات:** `npx supabase migration new <name>` ← SQL متوافق مع الإصدار السابق ← PR (يطبق CI الهجرات على Postgres + pgvector حقيقي) ← `npx supabase db push` قبل دمج الكود ← مستشار MCP. إن تعذّر تشغيل `npx supabase` فطبّق الملف عبر Supabase MCP `apply_migration`، ثم أعد تسمية ملف الهجرة في المستودع بالإصدار الذي سجله (`list_migrations`). الجدول الجديد في `src/db.py` يُوسم `info={'migration': ...}` حتى لا يتغير ملف الهجرة الأولى المولّد؛ وCI يفشل إن اختلفت `schemas/` أو `supabase/migrations/` عن المولّد من الكود.
- **مراجع جديد:** ينشئ حسابه بنفسه من الصفحة العامة (الاسم والبريد وكلمة المرور). الحسابات تراجع وتعتمد؛ ملف التدريب ومجموعات الاختبار والتقييم وتوثيق المراحل وإعادة الفهرسة لمسؤول المشروع فقط (رمز تشغيل من `create_reviewer.py`، أو بريد مُدرج في `ADMIN_EMAILS`). لإيقاف التسجيل: `SIGNUP_ENABLED=0`.
- **رمز تشغيل جديد:** `create_reviewer.py ... --env-file .env.production.local --token-out ...` ← حدّث `REVIEWER_TOKEN_HASHES` في Vercel ← أعد النشر.
- **مهام ثقيلة:** محليًا عبر `python -m src.cli` على Supabase.
- **نسخ احتياطي أسبوعي:** `npx supabase db dump --linked -f backups/$(date +%F).sql`.
