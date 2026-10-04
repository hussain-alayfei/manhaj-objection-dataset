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

1. أنشئ مشروع `manhaj` في `eu-central-1` (MCP `create_project` أو لوحة التحكم).
2. من اللوحة: Database ← Reset password (كلمة طويلة حروفًا وأرقامًا فقط)، وانسخ من **Connect** سلسلتي session (`:5432`) وtransaction (`:6543`) كما هما، والمفتاح **secret** من API Keys. لا تُلصق في المحادثة.
3. من طرفيتك:

```bash
npx supabase login
npx supabase link --project-ref <ref>
npx supabase db push
npx supabase migration list
```

التحقق عبر MCP: 20 جدولًا في `public`، امتداد `vector` في `extensions`، الحاوية `sources` خاصة، وملاحظات `rls_enabled_no_policy` متوقعة (RLS مفعّل بلا سياسات عمدًا؛ التطبيق يتصل بصفته مالك الجداول).

## 3. Vercel

```bash
npx vercel@latest login
npx vercel link --yes --project manhaj
npx vercel git connect
```

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
| `DATABASE_URL` | `postgresql+psycopg://postgres.<ref>:<pw>@<pooler-host>:6543/postgres` | نفسه |
| `READ_ONLY` | — | `1` |
| `REVIEWER_TOKEN_HASHES` | السطر من `.env.production.local` | نفسه |
| `OPENAI_API_KEY` | مفتاح مشروع OpenAI مع حد إنفاق شهري | نفسه |
| `LLM_PROVIDER` / `DIAGNOSIS_MODEL` / `DIAGNOSIS_REASONING_EFFORT` | `openai` / `gpt-6.1-sol` / `low` | `openai` / `gpt-6-luna` / `low` |
| `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` / `EMBEDDING_DIM` | `openai` / `text-embedding-3-small` / `768` | نفسه |
| `STORAGE_BACKEND` / `SUPABASE_URL` / `SUPABASE_SECRET_KEY` / `SUPABASE_STORAGE_BUCKET` | `supabase` / رابط المشروع / المفتاح السري / `sources` | نفسه |
| `DIAGNOSE_DAILY_LIMIT` | `50` | `10` |

ملف `.env` المحلي يحمل القيم نفسها، لكن `DATABASE_URL` على session pooler `:5432`، ودون `READ_ONLY`.

## 5. بذر قاعدة Supabase (محليًا)

```bash
mkdir -p work && cp data/source/SRC-e209f0cca8a26244/original.pdf work/book.pdf   # لا تمرر المسار الأصلي (SameFileError)
python scripts/seed_book.py work/book.pdf
python scripts/verify_dataset.py
python scripts/upload_source_pdf.py SRC-e209f0cca8a26244
python -m src.cli embeddings --include-drafts
```

المتوقع: 253 مقطعًا، 103 شبهات، 14 قاعدة، 240 إصدارًا. سجلات التدقيق غير قابلة للحذف؛ إعادة التشغيل آمنة (idempotent)، أما التصفير الكامل `npx supabase db reset --linked` فمدمّر ويحتاج قرار المالك.

## 6. التحقق بعد النشر

- `/health` = 200، دخول كل رمز، الملخص 103/14/117.
- فتح PDF من المصادر (يفتح رابطًا موقّعًا في نافذة جديدة).
- تشخيص بوضع المسودات يعيد تحليل GPT موسومًا «مسودة» مع الصفحات؛ الوضع المعتمد يمتنع (`no_approved_methodology`) حتى تُعتمد قواعد.
- لا تجرِ اعتمادات تجريبية في الإنتاج؛ اختبارات الكتابة تُجرى محليًا.
- المعاينة: القراءة تعمل والكتابة 403.

## العمل المستمر

- **قاعدة البيانات:** `npx supabase migration new <name>` ← SQL متوافق مع الإصدار السابق ← اختبار محلي (Docker) ← PR ← `npx supabase db push` قبل دمج الكود ← مستشار MCP.
- **مراجع جديد:** `create_reviewer.py ... --env-file .env.production.local --token-out ...` ← حدّث `REVIEWER_TOKEN_HASHES` في Vercel ← أعد النشر.
- **مهام ثقيلة:** محليًا عبر `python -m src.cli` على Supabase.
- **نسخ احتياطي أسبوعي:** `npx supabase db dump --linked -f backups/$(date +%F).sql`.
