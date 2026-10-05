"""Arabic wording for errors that reach reviewers. Internals and tests keep the English originals."""
import re

EXACT = {
    'Missing source spans': 'لا يوجد موضع محفوظ للنص في الكتاب.',
    'Source metadata mismatch': 'بيانات المصدر لا تطابق الكتاب المحفوظ.',
    'Source URL mismatch': 'رابط المصدر لا يطابق المحفوظ.',
    'Page/source mismatch': 'رقم الصفحة لا يطابق موضع النص في الكتاب.',
    'Excerpt not present at exact offsets': 'المقتطف غير موجود في موضعه من الكتاب.',
    'Excerpt is not the cited evidence': 'المقتطف لا يطابق النص المستشهد به.',
    'First page mismatch': 'رقم الصفحة الأولى لا يطابق الكتاب.',
    'New records must enter human review': 'السجلات الجديدة تدخل المراجعة أولًا.',
    'Unknown reviewer': 'حسابك غير معروف. سجّل الدخول من جديد.',
    'Record changed; reload before saving': 'عدّل شخص آخر هذا السجل قبلك. أغلق النافذة وافتحه من جديد.',
    'Concurrent update': 'عدّل شخص آخر هذا السجل في اللحظة نفسها. افتحه من جديد.',
    'Source evidence and provenance are immutable; re-ingest a corrected extraction': 'نص الكتاب ومصدره لا يُعدَّلان من هنا.',
    'Diagnosis attestation required': 'قبل الاعتماد علّم مربع «راجعت الدعوى والتشخيص».',
    'Source and page attestation required': 'قبل الاعتماد علّم مربعي «المقتطف مطابق للكتاب» و«رقم الصفحة صحيح».',
    'Exact objection wording must be selected from the source excerpt; use central claim for paraphrases': 'نص الشبهة يجب أن يكون منقولًا حرفيًا من مقتطف الكتاب. ضع إعادة الصياغة في «ما يدّعيه المعترض».',
    'Complete diagnosis fields before approval': 'أكمل قبل الاعتماد: ما يدّعيه المعترض، وسبب التشخيص، والسؤال الكاشف، وطريقة المعالجة.',
    'Link approved source methodology rules': 'اربط الشبهة بقاعدة معتمدة من الكتاب قبل اعتمادها.',
    'Methodology rule is not approved Phase 1 evidence': 'القاعدة المرتبطة لم تُعتمد بعد. اعتمد القاعدة أولًا.',
    'Rule text required': 'اكتب نص القاعدة.',
    'Rule text must be quoted from the source excerpt; put paraphrases in the diagnosis fields': 'نص القاعدة يجب أن يكون منقولًا حرفيًا من مقتطف الكتاب.',
    'Family claim and examples required': 'اكتب الدعوى المشتركة واختر أمثلة المجموعة.',
    'Approve family members first': 'اعتمد شبهات المجموعة أولًا.',
    'Machine proposal cannot change evidence or governance': 'لا يمكن للاقتراح الآلي تغيير النص أو حالة المراجعة.',
    'Invalid kind': 'نوع السجل غير صحيح.',
    'Invalid filter': 'خيار التصفية غير صحيح.',
    'Invalid pagination': 'خيارات الصفحة أو البحث غير صحيحة.',
    'Search text must be 1 to 2000 characters': 'نص البحث من حرف إلى 2000 حرف.',
    'Semantic index is not configured (EMBEDDING_MODEL)': 'البحث بالمعنى غير مفعّل.',
    'Run duplicate analysis first': 'شغّل البحث عن المكرر أولًا.',
    'PDF exceeds 50 MB': 'ملف PDF أكبر من 50 ميغابايت.',
    'Expected a PDF file': 'اختر ملف PDF.',
    'Choose automatic splitting or explicit holdout IDs, not both': 'اختر التقسيم الآلي أو أرقام الحالات، لا كليهما.',
    'Select approved manual benchmark cases': 'اختر حالات معتمدة لمجموعة الاختبار.',
    'Only eligible approved cases may enter a benchmark': 'مجموعة الاختبار تقبل الحالات المعتمدة فقط.',
    'Family spans test and validation': 'شبهات المجموعة الواحدة لا تتوزع بين الاختبار والتحقق.',
    'Benchmark contamination: case already exported for training': 'هذه الحالة صُدّرت للتدريب من قبل، فلا تدخل الاختبار.',
    'Benchmark family already used for training': 'مجموعة هذه الحالة استُخدمت في التدريب.',
    'Evaluate only a held-out split': 'التقييم على حالات الاختبار أو التحقق فقط.',
    'Predictions contain cases outside benchmark': 'النتائج تحتوي حالات خارج مجموعة الاختبار.',
    'Benchmark approval/version changed; create a new manifest': 'تغيّرت حالات المجموعة بعد إنشائها. أنشئ مجموعة جديدة.',
    'Human metrics require reviewer attribution and binary score': 'تقييم المراجع يحتاج اسم المراجع ودرجة 0 أو 1.',
    'Sub-pattern does not belong to the selected taxonomy root': 'تفصيل التشخيص لا يتبع التشخيص المختار.',
    'Record not found': 'السجل غير موجود.',
}
PATTERNS = [
    (re.compile(r'^Unknown methodology rule: (.+)$'), 'القاعدة {0} غير موجودة.'),
    (re.compile(r'^Unknown family example: (.+)$'), 'المثال {0} غير موجود.'),
    (re.compile(r'^(.+) is not a methodology rule$'), '{0} ليس قاعدة منهجية.'),
    (re.compile(r'^(.+) is not an objection$'), '{0} ليس شبهة.'),
    (re.compile(r'^Small dataset'), 'البيانات قليلة: اختر حالات الاختبار يدويًا.'),
    (re.compile(r'^Prediction for (.+) must be'), 'نتيجة الحالة {0} بصيغة غير صحيحة.'),
]


def arabic(message: str) -> str:
    """Arabic text for a known message; anything else passes through (already Arabic or unexpected)."""
    if message in EXACT: return EXACT[message]
    for pattern, template in PATTERNS:
        m = pattern.match(message)
        if m: return template.format(*m.groups())
    if re.search(r'[؀-ۿ]', message): return message
    # pydantic/model validation text is technical: give a plain instruction instead
    return 'تحقق من البيانات المدخلة ثم حاول مرة أخرى.'
