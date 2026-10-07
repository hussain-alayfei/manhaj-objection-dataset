# دليل النشر: GitHub + Supabase + Vercel + OpenAI

```
المتصفح (المراجعون) ─HTTPS─► Vercel fra1 · FastAPI (src/asgi.py) + web/
                               ├─► Supabase eu-central-1 · Postgres + pgvector (transaction pooler :6543)
                               ├─► Supabase Storage · حاوية خاصة "sources" ◄─ رابط موقّع 60 ثانية لعرض PDF
                               └─► OpenAI · responses.parse(gpt-6.1-sol, store=False) · embeddings(3-small@768)
سطر الأوامر المحلي (إدخال، استخراج آلي، فهرسة كاملة، تكرار/عائلات، نسخ احتياطي) ─► Supabase (session pooler :5432)
GitHub (خاص) ─► CI ─► Vercel: main → Production · PR → Preview للقراءة فقط
supabase/migrations/*.sql ─(npx supabase db push، قبل دمج الكود المعتمد عليها)─► Supabase
```

| الأداة | الاستخدام |
|---|---|
| `gh` | إنشاء المستودع، الدفع، طلبات الدمج، حالة CI |
| `npx supabase` | `link`، `migration new`، `db push`، `db dump` |
| Supabase MCP | إنشاء المشروع، الجداول، الامتدادات، المستشار الأمني، السجلات، استعلامات قراءة |
| `npx vercel` | `login`، `link`، `git connect`، `env add`، `deploy` |
| Vercel MCP | حالة النشر، سجلات البناء والتشغيل، ملفات الحزمة |

## 1. GitHub

```bash
git init -b main
git add -A && git status        # لا PDF ولا .db ولا .env ولا data/* سوى README/.gitkeep
gh repo create hussain-alayfei/manhaj-objection-dataset --private --source . --push
```

بعد ذلك: فرع ← `gh pr create` ← CI + معاينة Vercel ← دمج إلى main ← الإنتاج.

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

التحقق عبر MCP: 20 جدولًا في `public`، امتداد `vector` في `extensions`، الحاوية `sources` خاصة، وملاحظات `rls_enabled_no_policy` متوقعة (RLS مفعّل بلا سياسات عمدًا؛ التطبيق يتصل بصفته مالك الجداول).

## 3. Vercel

أداة Vercel MCP لا تملك صلاحية إنشاء مشروع في نطاق الحساب، لذا الربط من سطر الأوامر بعد تسجيل الدخول:

```bash
npx vercel@latest login
npx vercel link --yes --project manhaj
npx vercel git connect
```

إن لم يظهر المستودع الخاص، امنح تطبيق Vercel على GitHub صلاحية الوصول إليه.

`vercel.json` يثبت المنطقة `fra1` و`maxDuration: 300`، و`pyproject.toml` يحدد `src.asgi:app`. نشر تجريبي بلا أسرار حقيقية:

```bash
npx vercel deploy -e DATABASE_URL=sqlite:////tmp/smoke.db -e ALLOW_SQLITE_SMOKE=1 -e REVIEWER_TOKEN_HASHES='{"smoke":"<sha256>"}'
```

## 4. الأسرار (يُدخلها المالك)

رموز المراجعين للإنتاج (لا تُطبع؛ سلّم كل ملف لصاحبه ثم احذفه):

```bash
python scripts/create_reviewer.py hussain     --env-file .env.production.local --token-out work/token-hussain.txt
python scripts/create_reviewer.py reviewer-02 --env-file .env.production.local --token-out work/token-reviewer-02.txt
python scripts/create_reviewer.py reviewer-03 --env-file .env.production.local --token-out work/token-reviewer-03.txt
```

ثم لكل متغير: `npx vercel env add <NAME> production` (و`preview`):

| المتغير | Production | Preview |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://postgres.<ref>:<pw>@<pooler-host>:6543/postgres` | `sqlite:////tmp/preview.db` مع `ALLOW_SQLITE_SMOKE=1` |
| `READ_ONLY` | — | `1` |
| `REVIEWER_TOKEN_HASHES` | السطر من `.env.production.local` | نفسه |
| `OPENAI_API_KEY` | مفتاح مشروع OpenAI مع حد إنفاق شهري | — (لا يُضبط) |
| `LLM_PROVIDER` / `DIAGNOSIS_MODEL` / `DIAGNOSIS_REASONING_EFFORT` | `openai` / `gpt-6.1-sol` / `low` | `none` |
| `CRITIC_MODEL` / `SOURCE_CHECK_TIMEOUT` | اختياريان: المراجع الناقد على نموذج التحليل نفسه، ومهلة التحقق 6 ثوانٍ | — |
| `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` / `EMBEDDING_DIM` | `openai` / `text-embedding-3-small` / `768` | نفسه |
| `STORAGE_BACKEND` / `SUPABASE_URL` / `SUPABASE_SECRET_KEY` / `SUPABASE_STORAGE_BUCKET` | `supabase` / رابط المشروع / المفتاح السري / `sources` | `local` (دون المفتاح السري) |
| `DIAGNOSE_DAILY_LIMIT` | `50` | `10` |
| `DIAGNOSE_GLOBAL_DAILY_LIMIT` | `200` (كل الحسابات معًا) | — |
| `ASK_DAILY_LIMIT` | `60` (أسئلة المتابعة لكل حساب، الافتراضي إن لم يُضبط) | — |
| `SIGNUP_ENABLED` | `1` (أي شخص ينشئ حسابًا ويراجع) | `1` |
| `ADMIN_EMAILS` | بريد مسؤول المشروع، مفصولًا بفواصل | — |

ملف `.env` المحلي يحمل القيم نفسها، لكن `DATABASE_URL` على session pooler `:5432`. **النسخة المحلية من الموقع تعمل للقراءة فقط تلقائيًا** عندما تشير إلى قاعدة بعيدة (الإنتاج)، لأن الاعتماد وسجل التدقيق لا يُحذفان؛ للكتابة المقصودة اضبط `ALLOW_REMOTE_WRITES=1` مؤقتًا. أوامر سطر الأوامر (`seed_book.py` و`upload_source_pdf.py` و`src.cli`) تكتب عمدًا، فشغّلها فقط وأنت تقصد الإنتاج.

**نسخ المعاينة (Preview):** تعمل على قاعدة SQLite مؤقتة فارغة دون مفاتيح الإنتاج، فلا يستطيع أي فرع تجريبي الكتابة في قاعدة الإنتاج أو الصرف من OpenAI.

## 5. بذر قاعدة Supabase (محليًا)

```bash
mkdir -p work && cp data/source/SRC-e209f0cca8a26244/original.pdf work/book.pdf   # لا تمرر المسار الأصلي (SameFileError)
python scripts/seed_book.py work/book.pdf
python scripts/verify_dataset.py
python scripts/upload_source_pdf.py SRC-e209f0cca8a26244
python scripts/render_source_pages.py SRC-e209f0cca8a26244   # صور الصفحات لعارض الكتاب داخل الموقع
python -m src.cli embeddings --include-drafts
```

المتوقع: 253 مقطعًا، 103 شبهات، 14 قاعدة، 240 إصدارًا. سجلات التدقيق غير قابلة للحذف؛ إعادة التشغيل آمنة (idempotent)، أما التصفير الكامل `npx supabase db reset --linked` فمدمّر ويحتاج قرار المالك.

## 6. التحقق بعد النشر

- `/health` = 200، دخول كل رمز، الملخص 103/14/117.
- فتح PDF من المصادر (يفتح رابطًا موقّعًا في نافذة جديدة).
- تشخيص بوضع المسودات يعيد تحليل GPT موسومًا «مسودة» مع الصفحات؛ الوضع المعتمد يمتنع (`no_approved_methodology`) حتى تُعتمد قواعد.
- لا تجرِ اعتمادات تجريبية في الإنتاج؛ اختبارات الكتابة تُجرى على نسخة SQLite محلية (`DATABASE_URL=sqlite:///work/test.db`).
- المعاينة: القراءة تعمل والكتابة 403.

## العمل المستمر

- **قاعدة البيانات:** `npx supabase migration new <name>` ← SQL متوافق مع الإصدار السابق ← PR (يطبق CI الهجرات على Postgres + pgvector حقيقي) ← ← `npx supabase db push` قبل دمج الكود ← مستشار MCP.
- **مراجع جديد:** ينشئ حسابه بنفسه من صفحة البداية (الاسم والبريد وكلمة المرور). الحسابات تراجع وتعتمد؛ التصدير وإنشاء مجموعات الاختبار وتوثيق المراحل لمسؤول المشروع فقط (رمز تشغيل من `create_reviewer.py`، أو بريد مُدرج في `ADMIN_EMAILS`). لإيقاف التسجيل: `SIGNUP_ENABLED=0`.
- **رمز تشغيل (للأوامر والمسؤول):** `create_reviewer.py ... --env-file .env.production.local --token-out ...` ← حدّث `REVIEWER_TOKEN_HASHES` في Vercel ← أعد النشر.
- **مهام ثقيلة:** محليًا عبر `python -m src.cli` على Supabase.
- **نسخ احتياطي أسبوعي:** `npx supabase db dump --linked -f backups/$(date +%F).sql`.
