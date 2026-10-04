# مَنْهَج — Manhaj

**تشخيص بنية الشبهة قبل بناء مسار المعالجة.** مستودع بيانات ومراجعة عربية؛ لا ينشر إجابات دينية ولا يصدر فتاوى ولا يحكم على إيمان الأشخاص.

```
شبهة → تحرير الدعوى → تحديد المقارنة → تشخيص أصل الخلل
      → القاعدة المنهجية → المصدر → مسار المعالجة → مراجعة بشرية
```

## حالة التسليم

النسخة المحلية تتضمن استخراجًا أوليًا من **كتاب وليد**: «تربية الملكة على رد الشبهة»، لوليد بن راشد السعيدان، من PDF المستخدم. 152 صفحة PDF، 253 مقطعًا، 103 فروع أمثلة مرشحة، و14 مقطعًا مرشحًا لقواعد. أضيفت إلى 20 مثالًا مقترحات تحليلية منظمة بعد قراءة مقاطعها، تشمل الدعوى والمقارنة والسؤال وسبب التشخيص؛ لا تعد مراجعات بشرية. جميع السجلات `needs_review`، ولا يوجد اعتماد بشري مفترض. القواعد قد تتداخل وتحتاج تحرير حدودها. فروع الكتاب تشمل تكرار بعض أرقام الفروع؛ المعرفات مستقلة عن أرقام العناوين.

هذه نسخة V1 قابلة للتشغيل والمراجعة، مع مسار نشر PostgreSQL واختبارات حماية البيانات. **ليست إصدارًا إنتاجيًا معتمدًا بعد**: يلزم اعتماد الخبراء، والتحقق من PostgreSQL/pgvector في بيئة النشر، وضبط نموذج عربي وقياسه. الاستخراج الأول محافظ يعتمد عناوين الفروع ومؤشرات نصية، ولا يدعي اكتشاف كل قضية ضمنية أو دقة التحرير الدلالي. تقرير تغطية جميع المقاطع متاح للمراجعة.

المصدر والبيانات المشتقة محفوظة محليًا وخارجة عن Git افتراضيًا. لا تتضمن رخصة الكود ترخيصًا للكتاب. مع `LLM_PROVIDER=openai` تُرسل المقتطفات المسترجعة ونص الشبهة إلى OpenAI (`store=False`)؛ دون ذلك لا يُرسل الكتاب إلى أي خدمة نماذج. النشر المستضاف (GitHub خاص + Supabase + Vercel) موثق في [دليل النشر](docs/deployment.md).

## التشغيل المحلي — Python 3.12

نفذ الأوامر من جذر `manhaj-objection-dataset`:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
Copy-Item .env.example .env
python scripts/create_reviewer.py reviewer-01
python -m src.cli init-db
uvicorn src.asgi:app --host 127.0.0.1 --port 8000
```

افتح <http://127.0.0.1:8000> وأدخل رمز المراجع الذي طُبع مرة واحدة. احتفظ به في مدير كلمات مرور. لا توجد كلمة مرور افتراضية، ولا شاشة تسجيل حساب عام. يُخزن تجزئة الرمز فقط. لإنشاء مراجع آخر استخدم معرفًا مستقلًا وأعد تشغيل الخدمة.

Linux/macOS: استخدم `source .venv/bin/activate` و`cp .env.example .env`. إذا كانت `.env` موجودة فلا تستبدلها. قاعدة SQLite الموجودة في التسليم الخاص تعمل من هذا المجلد؛ لإعادة البناء استخدم مسار قاعدة جديدًا بدل محو سجل المراجعة.

### إدخال الكتاب وإعادة بناء بيانات البداية

```powershell
python scripts/seed_book.py "C:/Users/96650/Downloads/15110.pdf"
python scripts/verify_dataset.py
```

يعمل الإدخال بتجزئة SHA-256 لمنع تكرار الملف، ويعمل الاستخراج بمعرفات مشتقة من مواضع المصدر. لا تعيد الأوامر اعتماد أي سجل. تخزين أرقام الصفحات هو **PDF 1-based**؛ `printed_page_number=null` حتى التحقق، ولا يُستنتج رقم مطبوع.

لملف آخر:

```sh
python scripts/ingest_book.py book.pdf --title "اسم المصدر" --author "كما ورد في المصدر"
python -m src.cli extract SRC-identifier
```

استخدم `--profile rtl_visual` فقط إذا أظهر الفحص أن الملف يخزن الحروف بصريًا بصورة معكوسة. هذا الملف المرفق يحتاج ذلك؛ يحتفظ النظام بالنص الخام وبالنص المرتب منفصلين. نصوص OCR تبقى غير معتمدة. مسار OCR المحلي الاختياري موضح في [وثيقة الإدخال](docs/ingestion.md).

## المراجعة

1. افتح **المصادر** وافحص الأصل والمقاطع.
2. راجع **القواعد المنهجية** أولًا: حدد ما يقرره المؤلف وما ينقله عن المعترض.
3. في **المراجعة** حرر الدعوى والمقارنة والتصنيف والسؤال الكاشف، واربط القواعد المعتمدة.
4. تحقق من المقتطف والصفحة وصحة التشخيص، ثم اعتمد أو ارفض. الحفظ العادي يعيد الحالة إلى `needs_review`.
5. كل تعديل ينتج إصدارًا وسجلًا باسم المراجع. لا يمكن تعديل النص الخام أو نسبته عبر واجهة تعديل التحليل.

لا يكتمل هدف V1 البشري (10–30 مثالًا منهجيًا و20–50 شبهة مراجعة و5–10 قواعد محررة) آليًا. الـ117 سجلًا المرشحًا هي قائمة عمل لتحديد هذه المجموعة، وليست بيانات تدريب معتمدة.

## الاسترجاع والتشخيص

الاسترجاع يجمع BM25 مع تشابه المتجهات، ثم RRF وترتيبًا ثانيًا بتغطية كلمات السؤال، مع مرشحات المصدر والنمط والمرحلة والوسوم. تضمين حقول مستقل لنص الشبهة والدعوى والقاعدة والمقتطف وملخص العائلة. يقبل السجلات المعتمدة فقط افتراضيًا، ويتجاهل المتجهات القديمة بعد تعديل السجل. وضع المسودات (`include_drafts`) اختياري لكل تشخيص ويوسم ناتجه «مسودة».

الوضع الافتراضي بحث لفظي صريح، **ولا يُسمى بحثًا دلاليًا**. الإعداد المعتمد للنسخة المستضافة (OpenAI):

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=<from your OpenAI project>
DIAGNOSIS_MODEL=gpt-6.1-sol
DIAGNOSIS_REASONING_EFFORT=low
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=768
```

أو محليًا عبر Ollama: `LLM_PROVIDER=ollama`، `EMBEDDING_PROVIDER=ollama`، و`OLLAMA_URL`.

```sh
python -m src.cli embeddings --include-drafts   # incremental; unchanged fields are skipped
python scripts/find_duplicates.py
python scripts/create_families.py
```

يمكن استخدام `EMBEDDING_PROVIDER=sentence_transformers` بعد `pip install -e '.[semantic]'`. اختيار النموذج وتحميل أوزانه متروكان للمشغّل. يجب أن تطابق أبعاد المتجهات عمود `vector(768)`، أو تطبق هجرة جديدة قبل تغييرها. لا توجد متجهات عشوائية بديلة. لم تُحمّل أوزان نموذج ضمن التسليم.

يعمل المحلل (OpenAI بمخرجات منظمة صارمة، أو Ollama محليًا) بمخطط JSON، ثم يُفحص ناتجه وتُحل معرفات قواعده إلى مقتطفات معتمدة. أي اقتباس قاعدة يولده النموذج يستبدل بالنص المحفوظ. عند عدم وجود قواعد أو نموذج مضبوط، يُرجع `insufficient_evidence`. النتيجة دائمًا اقتراح داخلي يحتاج مراجعة.

## البحث الخارجي

`research_common_objections(topic, limit)` موجود في `src/research/pipeline.py`. يبحث في صفحات عامة ضمن قائمة روابط معتمدة في `config/external_sources.json`، وهي فارغة افتراضيًا. لا ينفذ بحثًا واسعًا غير مقيد، ولا يعتمد على ذاكرة النموذج.

لا يبدأ قبل إنهاء كل مرشحات المرحلة الأولى وتوثيق تغطية المصدر بواسطة المراجع. أي تعديل لاحق يبطل بوابة المرحلة الثانية. يلزم لكل مصدر تصريح وصول آلي، وتوثيق شروطه وأساس استخدامه واسم من راجع الحقوق. يفحص robots.txt، ويحترم تأخير الزحف، ويرفض التحويلات والعناوين الداخلية ويثبت عنوان الاتصال لمنع تبديل DNS. تحفظ الاقتباسات المحدودة والرابط والعنوان والتاريخ إن وُجد وتاريخ الجلب. النتائج والتكرارات والعائلات كلها مرشحة للمراجعة.

## التقييم والتصدير

```sh
# استبدل المعرفات بحالات معتمدة؛ أداة الواجهة توفر الإجراء نفسه
python scripts/build_benchmark.py --test-ids SHB-one SHB-two --validation-ids SHB-three
python scripts/run_baseline.py SPLIT-identifier
python scripts/export_training_jsonl.py SPLIT-identifier --output data/exports/train.jsonl
python -m src.cli snapshots
```

الملفات JSONL تستخدم `assistant.content` كسلسلة JSON صالحة، لملاءمة تنسيق المحادثات. التصدير مقيد ببيان إصدارات ثابت ويستبعد الاختبار والتحقق وعائلاتهما بشكل انتقالي، حتى عبر بيانات تقسيم أقدم. الحالات التي صدّرت للتدريب لا تصبح اختبارًا مستقلًا لاحقًا. التقييم لا يسترجع أمثلة الاختبار كأمثلة few-shot. لا fine-tuning في V1.

التقسيم التلقائي التقريبي 70/15/15 متاح فقط عند 100 حالة معتمدة على الأقل و20 مجموعة مستقلة على الأقل. الأصغر يستخدم حالات معيارية يختارها الخبير. المقاييس التسعة موجودة؛ المقاييس التي تحتاج تحكيمًا بشريًا تظهر `null/not_measured` قبل إدخال التحكيم، ولا تُختلق درجات.

## Supabase (PostgreSQL + pgvector) وVercel

```sh
npx supabase db push        # يطبق supabase/migrations على المشروع المرتبط
```

المخطط في [supabase/migrations](supabase/migrations)، ويشمل الجداول المطلوبة، إضافة إلى نسخ السجلات، والمتجهات، وبيانات التقسيم، وبوابات المراحل، وتشغيلات الاستخراج والتكرار، مع RLS وحاوية PDF خاصة. عارض SQLite للتطوير يستخدم طبقة التخزين نفسها؛ pgvector ينفذ حساب المسافة في PostgreSQL. تُحفظ embeddings مع معرف النموذج وإصدار السجل. CI يطبق الهجرات نفسها على PostgreSQL + pgvector حقيقي في GitHub Actions.

لا تنقل قاعدة SQLite إلى PostgreSQL بمجرد تغيير الرابط؛ أعد إدخال المصدر في قاعدة جديدة (`scripts/seed_book.py`) أو اكتب ترحيلًا خاضعًا للتدقيق للمراجعات القائمة. لا تُحذف قاعدة المراجعات لاستبدالها ببذرة. الاستضافة على Vercel وخطوات النشر الكاملة في [دليل النشر](docs/deployment.md).

## الاختبارات

```sh
pytest -q
python scripts/verify_dataset.py
```

الاختبارات تستخدم أمثلة اصطناعية **غير دينية** خارج مجموعة المصدر. مسار CI يشغل PostgreSQL/pgvector حقيقيًا ويطبق SQL قبل الاختبارات. الاختبار الخاص به يتخطى محليًا إذا لم يحدد `TEST_POSTGRES_URL`. تحقق جميع اقتباسات البيانات يعني مطابقة النص المستخرج؛ لا يغني عن مقابلة كل صفحة مصورة بشريًا.

## بنية المستودع

```text
src/ingestion/           PDF + provenance
src/parsing/             Arabic normalization + source extraction
src/chunking/            exact, page-local semantic boundary chunks
src/retrieval/           approved-only BM25 + vector + reranking
src/classification/      structured diagnosis, abstention, source checks
src/duplicate_detection/ exact / paraphrase / underlying objection proposals
src/family_detection/    candidate families; no forced membership
src/research/            Phase 2 gates + allowlisted source collection
src/evaluation/          frozen group splits + nine metrics
src/export/              approved-only JSON / JSONL
web/                    Arabic RTL reviewer dashboard
schemas/                canonical JSON Schema
supabase/migrations/    PostgreSQL + pgvector + audit constraints + RLS
scripts/                reproducible commands
tests/                  unit, API, governance, database integration
data/                   private inputs, candidates, approved data, benchmark
docs/                   methodology, governance, review, evaluation, operations
```

## مستندات ومرجعيات التنفيذ

- [المنهج وحدود التصنيف](docs/methodology.md)
- [حوكمة البيانات](docs/data-governance.md) و[خطوات المراجعة](docs/review-process.md)
- [التقييم ومنع التسرب](docs/evaluation.md) و[سياسة المصادر](docs/source-policy.md)
- [تقرير التسليم والتحقق](docs/delivery-report.md)
- توثيق تقني رسمي: [استخراج PDF](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)، [pgvector](https://github.com/pgvector/pgvector)، [FastAPI على Vercel](https://vercel.com/docs/frameworks/backend/fastapi)، [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs)، [التضمين](https://docs.ollama.com/api/embed).

رخصة MIT للكود فقط. راجع [LICENSE](LICENSE) قبل مشاركة المصادر أو البيانات المشتقة.
