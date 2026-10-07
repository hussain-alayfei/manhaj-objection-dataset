# مَنْهَج (Manhaj)

**تشخيص بنية الشبهة قبل بناء مسار المعالجة.** موقع عربي لمراجعة الشبهات وتحليلها وفق منهج كتاب «تربية الملكة على كشف الشبهة» للشيخ وليد بن راشد السعيدان، وأصله: «الشريعة لا تفرّق بين المتماثلات، ولا تجمع بين المختلفات». لا ينشر إجابات دينية معتمدة، ولا يصدر فتاوى، ولا يحكم على إيمان الأشخاص؛ كل ما يكتبه النموذج اقتراح يراجعه مختص.

النسخة المستضافة: <https://manhaj-three.vercel.app> (Vercel مع Supabase وOpenAI). دليل الوكلاء البرمجيين: [AGENTS.md](AGENTS.md).

```
شبهة → تحرير الدعوى → الكيانات والأدلة → التحقق من المصادر → جمع النصوص → التحليل اللغوي
     → المقارنة الدلالية → القاعدتان الحاكمتان → الفرضيات واختبارها → خريطة الاستدلال
     → المراجع الناقد → الجواب الموثّق → مراجعة بشرية
```

## ما الذي يقدمه الموقع الآن

- **الصفحة العامة:** يراها الزائر قبل الدخول: الأصل الذي يقوم عليه الكتاب، ومثال من الكتاب (صفحة 66)، وجولة «كيف يفكر مَنْهَج» تتسع إلى ملء الشاشة مع التمرير وتعرض الخطوات الإحدى عشرة واحدة بعد أخرى، ثم دعوة لإنشاء حساب.
- **الحسابات والأدوار:** زائر < مراجع < مسؤول. يُنشئ أي شخص حسابه بالاسم والبريد وكلمة المرور (`SIGNUP_ENABLED=1`) فيصبح مراجعًا يحلّل ويراجع ويعتمد. المسؤول هو صاحب رمز تشغيل من `scripts/create_reviewer.py` أو حساب بريده في `ADMIN_EMAILS`، وله وحده ملف التدريب ومجموعات الاختبار والتقييم وتوثيق المراحل وإعادة الفهرسة. الزائر بلا حساب لا يرى إلا الصفحة العامة (إلا إذا فُعّل `PUBLIC_ACCESS=1`، وهو مغلق في الإنتاج). لكل حساب ملف شخصي (الاسم والبريد وكلمة المرور والصورة).
- **مساحة المراجعة:** نظرة عامة، والمصادر، وشبهات الكتاب، والقواعد المنهجية، والشبهات المتشابهة، والمراجعة، وشبهات من مصادر أخرى، والتقييم، وتصدير البيانات. نافذة السجل تعرض المقتطف وصفحته وتاريخ إصداراته، ولا يُقبل الاعتماد إلا بعد أن يشهد المراجع بثلاثة أمور: المقتطف مطابق للكتاب ومنسوب لقائله، ورقم الصفحة صحيح، وراجع الدعوى والتشخيص. صفحات «شبهات من مصادر أخرى» و«التقييم» و«تصدير البيانات» تبقى فارغة وتشرح سبب ذلك حتى يعتمد المختصون سجلات فعلًا.
- **«حلّل شبهة»:** مساحة على هيئة محادثة: قائمة التحليلات السابقة بجانب محادثة واحدة مفتوحة. تُكتب الشبهة فيظهر التحليل وهو يُكتب، خطوة واحدة في نافذتها، ولا تُفتح الخطوة التالية قبل أن تُكتب. ثم يظهر الجواب في صفحة مستقلة، ومعه «هل التحليل صحيح؟». بعد اكتمال التحليل يسأل القارئ عمّا يشاء فيه، ويأتيه الجواب مكتوبًا من التحليل نفسه ومصادره وحدها، ويُحفظ مع التحليل.
- **عارض الكتاب:** صفحات الكتاب الأصلية تُعرض داخل الموقع صفحتين متقابلتين (صفحة واحدة على الشاشات الضيقة)، وتُفتح من المصادر ومن الاستشهادات على الصفحة المذكورة.

## حالة البيانات

المصدر الوحيد في المرحلة الأولى **كتاب وليد**: «تربية الملكة على رد الشبهة» (العنوان كما في صفحة الكتاب الأولى؛ والموقع يكتب «كشف الشبهة»، ولم يُحسم الفرق بعد)، من PDF المستخدم: 152 صفحة PDF، و253 مقطعًا، و103 شبهات مرشحة، و14 قاعدة مرشحة. أضيفت إلى 20 مثالًا مقترحات تحليلية منظمة لا تُعد مراجعات بشرية، واقتُرحت مجموعات مرشحة للشبهات المتشابهة. جميع السجلات `needs_review`، و**عدد السجلات المعتمدة صفر** حتى يراجعها الخبراء؛ لا اعتماد آليًا ولا اعتماد بشريًا مفترضًا. القواعد قد تتداخل وتحتاج تحرير حدودها، وأرقام بعض الفروع مكررة في الكتاب؛ المعرفات مستقلة عن أرقام العناوين.

ليست هذه نسخة إنتاجية معتمدة علميًا بعد: يلزم اعتماد الخبراء، ثم قياس الدقة على حالات معتمدة. الاستخراج الأول محافظ يعتمد عناوين الفروع ومؤشرات نصية، ولا يدعي اكتشاف كل قضية ضمنية.

## سياسة البيانات

المصدر والبيانات المشتقة منه (PDF، وقواعد البيانات، وملفات `data/`، وصور الصفحات) محفوظة خارج Git ولا تُرفع مع النشر. لا تتضمن رخصة الكود ترخيصًا للكتاب. الأسرار في `.env` محليًا وفي متغيرات Vercel فقط.

مع `LLM_PROVIDER=openai` يُرسل إلى OpenAI نص الشبهة والقواعد والأمثلة المسترجعة ومقتطفات المكتبة الشاملة (`store=False`)، ويبحث النموذج في مواقع محددة (الشاملة، وتراث، والدرر السنية، وsunnah.com، وإسلام ويب، وquran.com). وتُرسل الألفاظ المقتبسة في الشبهة إلى واجهة تراث (Turath) للبحث في المكتبة الشاملة، وأرقام الآيات والأحاديث إلى alquran.cloud ومجموعة hadith-api للتحقق منها. دون مزود نماذج لا يُرسل الكتاب إلى أي خدمة. التفاصيل في [حوكمة البيانات](docs/data-governance.md).

## التشغيل المحلي (Python 3.12)

نفّذ الأوامر من جذر `manhaj-objection-dataset`:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[test,tools]"
Copy-Item .env.example .env
python scripts/create_reviewer.py reviewer-01
python -m src.cli init-db
uvicorn src.asgi:app --host 127.0.0.1 --port 8000
```

أو شغّل `scripts/start_local.ps1` الذي ينفذ الخطوات نفسها. افتح <http://127.0.0.1:8000>، وأنشئ حسابًا من الصفحة العامة ثم ادخل به. رمز التشغيل الذي يطبعه `create_reviewer.py` مرة واحدة شرط لتشغيل الخادم، ويُستعمل للأوامر وواجهة API (`Authorization: Bearer`)، لا لشاشة الدخول؛ احفظه في مدير كلمات مرور. يُخزن تجزئة الرمز فقط. لتكون مسؤولًا محليًا أضف بريد حسابك إلى `ADMIN_EMAILS` في `.env` وأعد تشغيل الخادم.

Linux/macOS: استخدم `source .venv/bin/activate` و`cp .env.example .env`. إذا كانت `.env` موجودة فلا تستبدلها. **انتبه:** إن كان `DATABASE_URL` في `.env` يشير إلى قاعدة الإنتاج، فالموقع المحلي يعمل للقراءة فقط تلقائيًا، أما أوامر سطر الأوامر فتكتب فيها فعلًا. لإعادة البناء استخدم قاعدة SQLite جديدة بدل محو سجل المراجعة.

### إدخال الكتاب وإعادة بناء بيانات البداية

```powershell
python scripts/seed_book.py work/book.pdf
python scripts/verify_dataset.py
python scripts/render_source_pages.py SRC-e209f0cca8a26244   # صور الصفحات لعارض الكتاب
```

انسخ PDF إلى `work/` أولًا، ولا تمرر مسار النسخة المحفوظة في `data/source` نفسه. يعمل الإدخال بتجزئة SHA-256 لمنع تكرار الملف، ويعمل الاستخراج بمعرفات مشتقة من مواضع المصدر. لا تعتمد الأوامر أي سجل. أرقام الصفحات **PDF 1-based**؛ `printed_page_number=null` حتى التحقق، ولا يُستنتج رقم مطبوع.

لملف آخر:

```sh
python scripts/ingest_book.py book.pdf --title "اسم المصدر" --author "كما ورد في المصدر"
python -m src.cli extract SRC-identifier
```

استخدم `--profile rtl_visual` فقط إذا أظهر الفحص أن الملف يخزن الحروف بصريًا بصورة معكوسة. كتاب وليد يحتاج ذلك؛ ويحتفظ النظام بالنص الخام وبالنص المرتب منفصلين. نصوص OCR تبقى غير معتمدة. مسار OCR المحلي الاختياري في [وثيقة الإدخال](docs/ingestion.md).

## المراجعة

1. افتح **المصادر** وافحص الأصل والمقاطع، أو افتح صفحات الكتاب في العارض.
2. راجع **القواعد المنهجية** أولًا: حدد ما يقرره المؤلف وما ينقله عن المعترض.
3. في **المراجعة** حرر الدعوى والمقارنة والتصنيف والسؤال الكاشف، واربط القواعد المعتمدة.
4. تحقق من المقتطف والصفحة وصحة التشخيص، وعلّم مربعات الشهادة الثلاثة، ثم اعتمد أو ارفض. الحفظ العادي يعيد الحالة إلى `needs_review`.
5. كل تعديل ينتج إصدارًا وسجلًا باسم المراجع، وسجل التدقيق لا يُحذف. لا يمكن تعديل النص الخام أو نسبته عبر واجهة التحليل.

هدف المرحلة الأولى البشري (من 10 إلى 30 مثالًا منهجيًا، ومن 20 إلى 50 شبهة مراجعة، ومن 5 إلى 10 قواعد محررة) لا يكتمل آليًا. السجلات المرشحة قائمة عمل لتحديد هذه المجموعة، وليست بيانات تدريب معتمدة. التفاصيل في [خطوات المراجعة](docs/review-process.md).

## التحليل بالخطوات الإحدى عشرة

1. يسترجع النظام القواعد والأمثلة الأقرب من الكتاب (المعتمدة وحدها، أو «كل قواعد الكتاب» وتُعلَّم النتيجة «مسودة»؛ والواجهة تختار الثاني ما دامت لا توجد قاعدة معتمدة).
2. يبحث في المكتبة الشاملة عبر تراث عن الألفاظ المقتبسة في متون الحديث وشروحها ومعاجم اللغة.
3. يكتب النموذج الخطوات بترتيبها في مخطط صارم، وتظهر كل خطوة حين تكتمل (`POST /api/diagnose/stream`)، وتُطابق الآيات والأحاديث بمصادرها آليًا.
4. يعترض «المراجع الناقد» (الخطوة العاشرة) على الجواب؛ فإن لم يصمد أُعيد التحليل مرة واحدة، وإن بقيت الملاحظات خُفّضت درجة الثقة.
5. لا يُقبل تصنيف دون قاعدة مسترجعة من الكتاب، ونص القاعدة يُستبدل بالنص المحفوظ، وتوقف بوابة الأمان أي فتوى أو تكفير.

الأسئلة بعد التحليل: `POST /api/diagnoses/{id}/ask`، تُجاب من التحليل وحده، بحد 20 سؤالًا لكل تحليل و`ASK_DAILY_LIMIT` لكل حساب في اليوم. شرح الخطوات في [المنهج](docs/methodology.md).

## الاسترجاع والنماذج

الاسترجاع يجمع BM25 مع تشابه المتجهات، ثم RRF وترتيبًا ثانيًا بتغطية كلمات السؤال. التضمين مستقل لنص الشبهة والدعوى والقاعدة والمقتطف وملخص العائلة. دون `EMBEDDING_MODEL` يكون البحث لفظيًا فقط، **ولا يُسمى بحثًا دلاليًا**. إعداد النسخة المستضافة:

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=<from your OpenAI project>
DIAGNOSIS_MODEL=gpt-6.1-sol
DIAGNOSIS_REASONING_EFFORT=low
CRITIC_MODEL=            # step 10; defaults to DIAGNOSIS_MODEL
FOLLOWUP_MODEL=          # follow-up questions; defaults to DIAGNOSIS_MODEL
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=768
```

أو محليًا عبر Ollama: `LLM_PROVIDER=ollama` و`EMBEDDING_PROVIDER=ollama` و`OLLAMA_URL` (دون بث الخطوات ودون أسئلة المتابعة، فهي لـOpenAI وحده).

```sh
python -m src.cli embeddings --include-drafts   # incremental; unchanged fields are skipped
python scripts/find_duplicates.py
python scripts/create_families.py
```

يمكن استخدام `EMBEDDING_PROVIDER=sentence_transformers` بعد `pip install -e '.[semantic]'`. يجب أن تطابق أبعاد المتجهات عمود `vector(768)`، أو تُطبق هجرة جديدة قبل تغييرها. لا توجد متجهات عشوائية بديلة. عند غياب قواعد مناسبة أو نموذج مضبوط يمتنع التحليل ويذكر السبب. النتيجة دائمًا اقتراح يحتاج مراجعة.

## البحث الخارجي

`research_common_objections(topic, limit)` في `src/research/pipeline.py`. يبحث في صفحات عامة ضمن قائمة روابط معتمدة في `config/external_sources.json`، وهي فارغة افتراضيًا. لا ينفذ بحثًا واسعًا غير مقيد، ولا يعتمد على ذاكرة النموذج.

لا يبدأ قبل إنهاء كل مرشحات المرحلة الأولى وتوثيق تغطية المصدر بواسطة المسؤول. أي تعديل لاحق يبطل بوابة المرحلة الثانية. يلزم لكل مصدر تصريح وصول آلي، وتوثيق شروطه وأساس استخدامه واسم من راجع الحقوق. يفحص robots.txt، ويحترم تأخير الزحف، ويرفض التحويلات والعناوين الداخلية ويثبت عنوان الاتصال لمنع تبديل DNS. النتائج والتكرارات والعائلات كلها مرشحة للمراجعة. في النسخة المستضافة يعمل البحث من سطر الأوامر فقط.

## التقييم والتصدير

```sh
# استبدل المعرفات بحالات معتمدة؛ صفحة التقييم توفر الإجراء نفسه للمسؤول
python scripts/build_benchmark.py --test-ids SHB-one SHB-two --validation-ids SHB-three
python scripts/run_baseline.py SPLIT-identifier
python scripts/export_training_jsonl.py SPLIT-identifier --output data/exports/train.jsonl
python -m src.cli snapshots
```

ملفات JSONL تستخدم `assistant.content` كسلسلة JSON صالحة. التصدير مقيد ببيان إصدارات ثابت ويستبعد الاختبار والتحقق وعائلاتهما، حتى عبر بيانات تقسيم أقدم. الحالات التي صُدّرت للتدريب لا تصبح اختبارًا مستقلًا لاحقًا. التقييم لا يسترجع أمثلة الاختبار كأمثلة few-shot. لا fine-tuning في V1.

التقسيم التلقائي التقريبي 70/15/15 متاح فقط عند 100 حالة معتمدة على الأقل و20 مجموعة مستقلة على الأقل. المقاييس التسعة موجودة؛ ما يحتاج تحكيمًا بشريًا يظهر `null/not_measured` قبل إدخال التحكيم، ولا تُختلق درجات. التفاصيل في [التقييم](docs/evaluation.md).

## Supabase (PostgreSQL + pgvector) وVercel

```sh
npx supabase db push        # يطبق supabase/migrations على المشروع المرتبط، قبل دمج الكود المعتمد عليها
```

المخطط في [supabase/migrations](supabase/migrations): السجلات ونسخها، والمراجعات، والمتجهات، وبيانات التقسيم، وبوابات المراحل، والتحليلات، والحسابات والجلسات، مع RLS وحاوية خاصة للـPDF وصور الصفحات. SQLite للتطوير يستخدم طبقة التخزين نفسها. سجلات المراجعة والإصدارات غير قابلة للتعديل أو الحذف (مشغلات SQL). CI يطبق الهجرات نفسها على PostgreSQL + pgvector حقيقي.

لا تنقل قاعدة SQLite إلى PostgreSQL بمجرد تغيير الرابط؛ أعد إدخال المصدر في قاعدة جديدة (`scripts/seed_book.py`) أو اكتب ترحيلًا خاضعًا للتدقيق. نسخ المعاينة (Preview) تعمل على SQLite فارغة للقراءة فقط دون أسرار الإنتاج. خطوات النشر والمتغيرات كلها في [دليل النشر](docs/deployment.md).

## الاختبارات

```sh
pytest -q
python scripts/verify_dataset.py
```

الاختبارات (نحو 150) تستخدم أمثلة اصطناعية **غير دينية** خارج مجموعة المصدر، ولا تتصل بالشبكة. CI يشغلها على كل طلب دمج مع PostgreSQL/pgvector حقيقي، ثم يتحقق أن `schemas/` و`supabase/migrations/` مولّدة من الكود. اختبار PostgreSQL يُتخطى محليًا إذا لم يحدد `TEST_POSTGRES_URL`. مطابقة الاقتباسات للنص المستخرج لا تغني عن مقابلة كل صفحة مصورة بشريًا.

## بنية المستودع

```text
src/api.py, asgi.py      FastAPI app, roles, streams, static files (Vercel entrypoint: src.asgi:app)
src/auth.py, db.py       accounts and sessions; one storage layer for SQLite and PostgreSQL
src/models.py            records, review requests, the eleven-step MethodProposal, CriticReport
src/classification/      the analysis pipeline, Shamela library (Turath), verse/hadith checks, follow-up answers
src/retrieval/           BM25 + vector + reranking
src/ingestion/           PDF + provenance
src/parsing/, chunking/  Arabic normalization, source extraction, page-local chunks
src/duplicate_detection/ exact / paraphrase / underlying objection proposals
src/family_detection/    candidate families; no forced membership
src/research/            phase 2 gates + allowlisted source collection
src/evaluation/          frozen group splits + nine metrics
src/export/              approved-only JSON / JSONL
web/                     Arabic RTL site: index.html, app.js, style.css (vanilla JS, no build step), img/, fonts/
schemas/                 JSON Schema generated from src/models.py
supabase/migrations/     PostgreSQL + pgvector + audit constraints + RLS
scripts/                 reproducible commands
tests/                   unit, API, governance, database integration
data/                    private inputs, candidates, approved data, benchmark (not in Git)
docs/                    methodology, governance, review, evaluation, deployment, operations
```

## المستندات

- [AGENTS.md](AGENTS.md): دليل الوكلاء البرمجيين (التشغيل، البنية، قواعد العمل، المزالق)
- [المنهج وحدود التصنيف](docs/methodology.md)
- [حوكمة البيانات](docs/data-governance.md) و[خطوات المراجعة](docs/review-process.md)
- [التقييم ومنع التسرب](docs/evaluation.md) و[سياسة المصادر](docs/source-policy.md) و[إدخال PDF](docs/ingestion.md)
- [دليل النشر](docs/deployment.md) و[التشغيل والإصدار](docs/operations.md)
- [تقرير التسليم](docs/delivery-report.md) و[تقرير المؤشرات](docs/kpi-report.md)
- توثيق تقني رسمي: [استخراج PDF](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)، [pgvector](https://github.com/pgvector/pgvector)، [FastAPI على Vercel](https://vercel.com/docs/frameworks/backend/fastapi)، [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs)، [التضمين](https://docs.ollama.com/api/embed).

رخصة MIT للكود فقط. راجع [LICENSE](LICENSE) قبل مشاركة المصادر أو البيانات المشتقة.
