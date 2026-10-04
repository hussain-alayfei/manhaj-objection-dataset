'use strict';
const $ = (s, root=document) => root.querySelector(s);
const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const titles = {overview:'نظرة عامة',sources:'المصادر',objections:'الشبهات المستخرجة',external:'الشبهات الخارجية',rules:'القواعد المنهجية',families:'عائلات الشبهات',review:'المراجعة',evaluation:'التقييم',export:'تصدير بيانات التدريب'};
const statuses={approved:'معتمد',needs_review:'يحتاج مراجعة',draft:'مسودة',rejected:'مرفوض'};
let token=sessionStorage.getItem('manhaj-token')||'', view='overview', offset=0, currentRecord=null, taxonomy={}, query='', status='', caps={};
const badge=s=>`<span class="pill ${s==='approved'?'':s==='rejected'?'rejected':'pending'}">${esc(statuses[s]||s)}</span>`;
function notify(message){$('#notice').textContent=message;$('#notice').hidden=false;setTimeout(()=>$('#notice').hidden=true,6500);}
async function api(path, options={}){
 const headers={Authorization:`Bearer ${token}`,...options.headers};
 if(options.body && !(options.body instanceof FormData)){headers['Content-Type']='application/json';options.body=JSON.stringify(options.body);}
 const response=await fetch('/api'+path,{...options,headers});
 if(!response.ok){let error;try{error=await response.json();}catch{error={detail:'تعذر إكمال الطلب'};}throw Error(typeof error.detail==='string'?error.detail:JSON.stringify(error.detail));}
 return options.blob?response.blob():response.json();
}
function title(name,subtitle,action=''){return `<div class="page-title"><div><div class="eyebrow">مَنْهَج / ${esc(titles[view])}</div><h2>${esc(name)}</h2><p>${esc(subtitle)}</p></div>${action}</div>`;}
async function init(){
 if(!token)return;
 try{const me=await api('/me');taxonomy=me.taxonomy;caps=me.capabilities||{};$('#identity').textContent=me.reviewer_id+(caps.read_only?' · معاينة للقراءة فقط':'');$('#login').hidden=true;$('#content').hidden=false;await render();}
 catch(e){sessionStorage.removeItem('manhaj-token');token='';$('#login').hidden=false;$('#content').hidden=true;notify(e.message);}
}
$('#login-form').addEventListener('submit',e=>{e.preventDefault();token=$('#token').value;sessionStorage.setItem('manhaj-token',token);$('#token').value='';init();});
$('#logout').addEventListener('click',()=>{sessionStorage.removeItem('manhaj-token');location.reload();});
$('#nav').addEventListener('click',e=>{const b=e.target.closest('[data-view]');if(b){view=b.dataset.view;offset=0;query='';status='';render().catch(e=>notify(e.message));}});

async function render(){
 if(!token)return;
 $('#breadcrumb').textContent=titles[view];
 document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
 if(view==='overview')return overview();
 if(view==='sources')return sourcesView();
 if(view==='evaluation')return evaluationView();
 if(view==='export')return exportView();
 return recordsView();
}
async function overview(){
 const [s,records]=await Promise.all([api('/summary'),api('/records?kind=objection&status=needs_review&limit=5')]);
 $('#content').innerHTML=title('التشخيص يبدأ بفهم الدعوى.','مساحة لبناء معرفة منهجية موثقة، خطوةً بخطوة.','<span class="pill">مصدر موثّق · مراجعة بشرية</span>')+
 `<div class="metrics">${[['المصادر',s.sources,'كتاب وليد · المصدر الأول'],['الشبهات المستخرجة',s.objections,'أمثلة مرشحة من نص المصدر'],['القواعد المنهجية',s.rules,'تُراجع قبل الاستخدام'],['بانتظار المراجعة',s.pending,`${s.approved} سجل معتمد`]].map(([label,n,note])=>`<div class="card metric"><div class="top">${label}<span>◌</span></div><strong>${n.toLocaleString('ar')}</strong><small>${note}</small></div>`).join('')}</div>
 <div class="hero"><div class="eyebrow">الفهم قبل المعالجة</div><h3>نبحث في بنية الشبهة، ونوثّق طريق التشخيص.</h3><p>نص المصدر، والاستنتاج التحليلي، واعتماد الخبير ثلاث طبقات مستقلة. لا تدخل أي حالة إلى التدريب قبل مراجعتها.</p><div class="path"><span>تحرير الدعوى</span>←<span>تحديد المقارنة</span>←<span>تشخيص الخلل</span>←<span>القاعدة والمصدر</span>←<span>مسار المعالجة</span></div></div>
 <div class="two-col"><section class="card"><div class="card-head"><h3>في قائمة المراجعة</h3><button class="quiet" data-go="review">عرض القائمة ←</button></div>${records.items.map((r,i)=>`<div class="row"><span class="num">${String(i+1).padStart(2,'0')}</span><div class="text"><h4>${esc(r.title_ar)}</h4><p>${esc(r.source?.source_name)} · صفحة PDF ${r.source?.page_number}</p></div><button data-open="${esc(r.id)}">مراجعة</button></div>`).join('')||'<div class="empty">لا توجد حالات معلقة.</div>'}</section>
 <section class="card"><div class="card-head"><h3>ضوابط المعرفة</h3><span class="pill">فعّالة</span></div><div class="principle"><b>01 · مدعوم من المصدر</b><p>مقتطف محفوظ مع الصفحة وموضعه في النص.</p></div><div class="principle"><b>02 · استنتاج تحليلي</b><p>التصنيف والتحرير مقترحان، ويجوز الامتناع عنهما.</p></div><div class="principle"><b>03 · يحتاج مراجعة</b><p>اعتماد بشري موثّق قبل التقييم أو التدريب.</p></div><div class="principle"><b>المرحلة الثانية</b><p>تبقى مغلقة حتى اكتمال مراجعة المصدر وتوثيق تغطيته.</p></div></section></div>
 <section class="card spaced"><h3>اختبار مسار التشخيص</h3><p class="muted">يعرض النظام استنتاجًا مقترحًا أو يمتنع عند نقص الأدلة المعتمدة.</p><form id="diagnose-form"><label for="diagnose-text">نص الشبهة</label><textarea id="diagnose-text" required maxlength="12000" placeholder="اكتب الدعوى التي تريد فحص بنيتها…"></textarea><label class="check"><input id="diagnose-drafts" type="checkbox">تضمين المسودات غير المعتمدة — النتيجة تُعلَّم «مسودة» ولا تُعد اعتمادًا</label><button class="primary spaced">تشخيص البنية</button>${caps.semantic&&!caps.read_only?' <button type="button" class="spaced" data-action="refresh-index">تحديث فهرس البحث</button>':''}</form><div id="diagnosis-result" class="spaced"></div></section>`;
}
async function recordsView(){
 const kind=view==='rules'?'rule':view==='families'?'family':view==='review'?'':'objection';
 const phase=view==='external'?2:view==='objections'?1:'';
 const chosen=status||(view==='review'?'needs_review':'');
 const params=new URLSearchParams({limit:'30',offset:String(offset),q:query});if(kind)params.set('kind',kind);if(phase)params.set('phase',phase);if(chosen)params.set('status',chosen);
 const data=await api('/records?'+params);
 let extra='';
 if(view==='external')extra=!caps.heavy_jobs?'<div class="banner">البحث الخارجي يعمل من سطر الأوامر فقط في النسخة المستضافة، وكل نتيجة تدخل قائمة المراجعة.</div>':`<div class="banner">البحث الخارجي يتطلب إنهاء مراجعة المرحلة الأولى وتوثيق التغطية؛ كل نتيجة تدخل قائمة المراجعة.</div><details class="card spaced"><summary>البحث في المصادر المسموح بها</summary><form id="research-form"><label for="research-topic">الموضوع</label><input id="research-topic" required><label for="research-limit">الحد الأقصى</label><input id="research-limit" type="number" min="1" max="50" value="5"><button class="primary spaced">جمع حالات موثقة</button></form><form id="gate-form"><label class="check"><input id="coverage-check" type="checkbox" required>أشهد باكتمال مراجعة جميع أمثلة وقواعد المصدر وفحص المقاطع غير المستخرجة.</label><label for="coverage-notes">تقرير تغطية المصدر</label><textarea id="coverage-notes" required></textarea><button class="spaced">توثيق اكتمال المرحلة الأولى</button></form></details>`;
 const actions=!caps.heavy_jobs?'':view==='families'?'<button data-action="families">اقتراح عائلات</button>':view==='objections'?'<button data-action="duplicates">فحص التكرار</button>':'';
 $('#content').innerHTML=title(titles[view],`${data.total.toLocaleString('ar')} سجل · يُفصل الدليل عن التشخيص المقترح`,actions)+extra+`<div class="toolbar spaced"><input id="search" aria-label="بحث" placeholder="ابحث في الدعوى أو العنوان…" value="${esc(query)}"><select id="status-filter" aria-label="حالة المراجعة"><option value="">جميع الحالات</option>${Object.entries(statuses).map(([k,v])=>`<option value="${k}" ${chosen===k?'selected':''}>${v}</option>`).join('')}</select><button data-action="filter">تصفية</button></div><section class="card"><div class="table-wrap"><table><thead><tr><th>الشبهة / القاعدة</th><th>نوع الخلل</th><th>المصدر والصفحة</th><th>الحالة</th><th></th></tr></thead><tbody>${data.items.map(r=>`<tr><td>${esc(r.title_ar)}<small dir="ltr">${esc(r.id)}</small></td><td>${esc(r.primary_pattern)}<small>${esc(r.sub_patterns.join('، '))}</small></td><td>${esc(r.source?.source_name||'تجميع تحليلي')}<small>${r.source?.page_number?'صفحة PDF '+r.source.page_number:'—'}</small></td><td>${badge(r.review_status)}</td><td><button data-open="${esc(r.id)}">فتح السجل</button></td></tr>`).join('')}</tbody></table>${data.items.length?'':'<div class="empty">لا توجد سجلات مطابقة. ابدأ بالمصدر ومراجعة قواعده.</div>'}</div><div class="pagination"><span>${data.total?offset+1:0}–${Math.min(offset+30,data.total)} من ${data.total}</span><div><button data-page="prev" ${offset===0?'disabled':''}>السابق</button> <button data-page="next" ${offset+30>=data.total?'disabled':''}>التالي</button></div></div></section>`;
}
async function sourcesView(){
 const sources=await api('/sources');
 $('#content').innerHTML=title('المصدر هو نقطة البداية.','نص أصلي محفوظ، وصفحات قابلة للتحقق، ومقاطع لا تفقد سياقها.')+`<div class="list-stack">${sources.map(s=>`<article class="card source-card"><div class="book-icon">▤</div><div class="text"><span class="eyebrow">${s.source_type==='book'?'المصدر الأساسي':'مصدر خارجي'}</span><h3>${esc(s.source_name)}</h3><p>${esc(s.actual_title||'')} · ${esc(s.author)}</p><p>${s.page_count||'—'} صفحة · ترقيم صفحات PDF يبدأ من 1</p><small dir="ltr">${esc(s.id)}</small></div><button data-source="${esc(s.id)}">عرض الأصل</button><button data-chunks="${esc(s.id)}">المقاطع</button></article>`).join('')}</div>${!caps.heavy_jobs?'<div class="banner spaced">إضافة المصادر تتم من سطر الأوامر في النسخة المستضافة (python scripts/ingest_book.py).</div>':`<details class="card spaced"><summary>إضافة مصدر PDF</summary><form id="ingest-form"><label for="pdf-title">اسم المصدر</label><input id="pdf-title" value="كتاب وليد" required><label for="pdf-author">المؤلف كما يظهر في المصدر</label><input id="pdf-author"><label for="pdf-profile">طريقة ترتيب النص</label><select id="pdf-profile"><option value="standard">استخراج قياسي</option><option value="rtl_visual">ملف بترتيب مرئي معكوس — مثل الكتاب المرفق</option></select><label for="pdf-file">ملف PDF</label><input id="pdf-file" type="file" accept="application/pdf" required><button class="primary spaced">استخراج إلى قائمة المراجعة</button></form></details>`}`;
}
async function evaluationView(){
 const [manifests,runs]=await Promise.all([api('/documents/dataset_manifests'),api('/documents/evaluation_runs')]);
 $('#content').innerHTML=title('اختبار مستقل عن التدريب.','في البيانات الصغيرة نختار حالات معيارية يدويًا، ونفصل العائلات بين المجموعات.')+`<div class="banner">لا توجد نتائج أداء مفترضة. المقاييس الدلالية تنتظر تحكيمًا بشريًا موثقًا.</div><div class="two-col"><section class="card"><h3>إنشاء معيار يدوي</h3><form id="benchmark-form"><label for="test-ids">معرّفات حالات الاختبار المعتمدة — سطر لكل حالة</label><textarea id="test-ids" required dir="ltr"></textarea><label for="validation-ids">معرّفات حالات التحقق — اختياري</label><textarea id="validation-ids" dir="ltr"></textarea><button class="primary spaced">حفظ مجموعة مستقلة</button></form></section><section class="card"><h3>مجموعات التقييم</h3>${manifests.map(m=>`<div class="row"><div><small dir="ltr">${esc(m.id)}</small><p>تدريب ${m.payload.training_ids.length} · تحقق ${m.payload.validation_ids.length} · اختبار ${m.payload.test_ids.length}</p></div></div>`).join('')||'<div class="empty">تُنشأ بعد اعتماد الحالات.</div>'}</section></div><section class="card spaced"><h3>نتائج التقييم</h3>${runs.map(r=>`<details><summary>${esc(r.id)}</summary><pre class="json">${esc(JSON.stringify(r.payload.metrics,null,2))}</pre></details>`).join('')||'<div class="empty">لم يُنفذ تقييم بعد.</div>'}</section>`;
}
async function exportView(){
 const [manifests,exports]=await Promise.all([api('/documents/dataset_manifests'),api('/documents/training_exports')]);
 $('#content').innerHTML=title('بيانات تعتمدها المراجعة.','تُصدّر الحالات المعتمدة فقط، وتُحجب حالات التقييم وعائلاتها عن التدريب.')+`<div class="two-col"><section class="card"><h3>تصدير JSONL للتدريب</h3><form id="export-form"><label for="manifest">مجموعة البيانات</label><select id="manifest" required><option value="">اختر مجموعة موثقة</option>${manifests.map(m=>`<option value="${esc(m.id)}">${esc(m.id)} · ${m.payload.training_ids.length} حالة تدريب</option>`).join('')}</select><button class="primary spaced">تنزيل بيانات التدريب</button></form><button data-action="json-export" class="spaced">تنزيل السجلات المعتمدة بصيغة JSON</button></section><section class="card"><h3>سجل التصدير</h3>${exports.map(x=>`<div class="row"><div><small>${esc(x.payload.at)}</small><p>${x.payload.records.length} حالة · بإصدارات ثابتة</p></div></div>`).join('')||'<div class="empty">لا توجد عمليات تصدير.</div>'}</section></div>`;
}
function field(id,label,value,rows=false){return `<label for="edit-${id}">${label}</label>${rows?`<textarea id="edit-${id}">${esc(value)}</textarea>`:`<input id="edit-${id}" value="${esc(value)}">`}`;}
async function openRecord(id){
 const [r,rules]=await Promise.all([api('/records/'+id),api('/records?kind=rule&status=approved&limit=200')]);currentRecord=r;
 const patterns=[...Object.keys(taxonomy),'mixed_pattern','multiple_claims','unknown','insufficient_evidence','requires_human_review'];
 $('#editor-content').innerHTML=`<div class="modal-head"><div><small dir="ltr">${esc(r.id)} · v${r.version}</small><h3>مراجعة ${r.kind==='rule'?'القاعدة':r.kind==='family'?'العائلة':'الحالة'} ${badge(r.review_status)}</h3></div><button data-action="close">إغلاق</button></div><div class="modal-grid"><section><div class="eyebrow">الطبقة الأولى · نص المصدر</div><div class="evidence"><h3>${esc(r.source?.source_name||'عائلة مقترحة')}</h3><div class="source-meta"><span>${esc(r.source?.author||'')}</span><span>${r.source?.page_number?'صفحة PDF '+r.source.page_number:''}</span><span>${esc(r.source?.section||'')}</span></div>${r.source?.source_type==='book'?`<button data-source="${esc(r.source.source_id)}" data-pdfpage="${r.source.page_number}">فتح الصفحة في الأصل</button>`:''}<div class="excerpt">${esc(r.source?.source_excerpt||r.common_variants_ar.join('\n\n'))}</div></div><h3 class="spaced">النص المرشح للشبهة</h3><p>${esc(r.objection_text_ar||'—')}</p><details class="spaced"><summary>أحدث مقترح آلي محفوظ</summary><pre class="json">${esc(JSON.stringify(r.ai_analysis,null,2))}</pre></details><button class="quiet spaced" data-history="${esc(r.id)}">عرض سجل الإصدارات ←</button><div id="history"></div></section><section><div class="eyebrow">الطبقة الثانية · تحرير المراجع</div><form id="review-form">${field('title_ar','العنوان',r.title_ar)}${r.kind==='objection'?field('objection_text_ar','نص الشبهة — اختر العبارة من المصدر',r.objection_text_ar,true):''}${field('central_claim_ar','الدعوى المركزية',r.central_claim_ar,true)}${field('subclaims_ar','الدعاوى الفرعية — سطر لكل دعوى',r.subclaims_ar.join('\n'),true)}${field('compared_entities_ar','طرفا المقارنة — كل سطر: الطرف الأول | الطرف الثاني',r.compared_entities_ar.map(x=>x.entity_a+' | '+x.entity_b).join('\n'),true)}<div class="fields-two"><div><label for="edit-pattern">نوع الخلل</label><select id="edit-pattern">${patterns.map(p=>`<option ${p===r.primary_pattern?'selected':''}>${esc(p)}</option>`).join('')}</select></div><div><label for="edit-subpatterns">الأنماط الفرعية</label><select id="edit-subpatterns" multiple size="4">${Object.values(taxonomy).flat().map(p=>`<option ${r.sub_patterns.includes(p)?'selected':''}>${esc(p)}</option>`).join('')}</select></div></div>${field('diagnostic_reason_ar','سبب التشخيص',r.diagnostic_reason_ar,true)}${field('revealing_question_ar','السؤال الكاشف',r.revealing_question_ar,true)}${r.kind==='rule'?field('methodology_rule_ar','نص القاعدة المرشحة',r.methodology_rule_ar,true):`<label for="edit-ruleids">القواعد المعتمدة المرتبطة</label><select id="edit-ruleids" multiple size="4">${rules.items.map(x=>`<option value="${esc(x.id)}" ${r.methodology_rule_ids.includes(x.id)?'selected':''}>${esc(x.title_ar)}</option>`).join('')}</select>`}${field('treatment_ar','المعالجة المنهجية',r.treatment_ar,true)}${field('response_path_ar','مسار المعالجة — سطر لكل خطوة',r.response_path_ar.join('\n'),true)}${r.kind==='family'?field('core_claim_ar','الدعوى المشتركة للعائلة',r.core_claim_ar,true)+field('core_confusion_ar','موضع الالتباس المشترك',r.core_confusion_ar,true):''}<details><summary>التكرار والعائلة</summary>${field('duplicate_group_id','معرف مجموعة التكرار',r.duplicate_group_id||'')}${field('family_id','معرف العائلة',r.family_id||'')}<label for="edit-similarity">نوع التشابه</label><select id="edit-similarity">${['exact_duplicate','paraphrase','same_underlying_objection','same_pattern_different_objection','new_case'].map(x=>`<option ${x===r.similarity_type?'selected':''}>${x}</option>`).join('')}</select></details>${field('notes','ملاحظات المراجع',r.reviewer_notes,true)}<div class="eyebrow spaced">الطبقة الثالثة · الاعتماد البشري</div><label class="check"><input id="verify-source" type="checkbox">تحققت من مطابقة المقتطف للمصدر ونسبة القول.</label><label class="check"><input id="verify-page" type="checkbox">تحققت من الصفحة في الأصل، أو من الرابط للمصدر الخارجي.</label><label class="check"><input id="verify-diagnosis" type="checkbox">راجعت تحرير الدعوى والتشخيص وحدود الدليل.</label><div class="actions"><button class="primary" name="action" value="approve">اعتماد السجل</button><button name="action" value="edit">حفظ للمراجعة</button><button class="danger" name="action" value="reject">رفض</button></div></form></section></div>`;
 $('#editor').showModal();
}
const abstentions={no_approved_methodology:'لا توجد قواعد معتمدة مطابقة؛ امتنع النظام عن التصنيف.',model_not_configured:'لم يُضبط نموذج التحليل.',model_or_grounding_validation_failed:'رُفض مقترح النموذج لعدم استناده إلى القواعد المرفقة.',retrieval_unavailable:'تعذر الوصول إلى خدمة البحث.',safety_gate:'أوقفت بوابة السلامة مخرجًا خارج التشخيص البنيوي.'};
function diagnosisHtml(r){
 const a=r.analysis,draft=r.mode==='draft',item=(label,value)=>value&&String(value).trim()?`<dt>${label}</dt><dd>${esc(value)}</dd>`:'';
 const list=(label,values)=>values&&values.length?`<dt>${label}</dt><dd><ol>${values.map(x=>`<li>${esc(x)}</li>`).join('')}</ol></dd>`:'';
 const cites=r.source_evidence.map(c=>`<li><span dir="ltr">${esc(c.record_id)}</span> · ${badge(c.review_status||'approved')} · ${esc(c.source?.source_name||'')} · صفحة PDF ${c.source?.page_number??'—'}</li>`).join('');
 const note=r.abstention_reason?(abstentions[r.abstention_reason]||r.abstention_reason):'استنتاج تحليلي مستند إلى القواعد المرفقة';
 const confidence=a.confidence!=null&&!r.abstention_reason?' · الثقة '+Math.round(a.confidence*100)+'%':'';
 const model=r.analysis_model?' · النموذج: <span dir="ltr">'+esc(r.analysis_model)+'</span>':'';
 return `<div class="banner">${draft?'<span class="pill pending">مسودة</span> ':''}${esc(a.primary_pattern)} · يحتاج مراجعة · ${esc(r.evidence_label_ar)}</div><dl class="diagnosis">${item('الدعوى المركزية',a.central_claim_ar)}${list('الدعاوى الفرعية',a.subclaims_ar)}${list('طرفا المقارنة',a.compared_entities_ar.map(x=>x.entity_a+' ⟷ '+x.entity_b))}${list('الأنماط الفرعية',a.sub_patterns)}${item('سبب التشخيص',a.diagnostic_reason_ar)}${item('السؤال الكاشف',a.revealing_question_ar)}${item('نص القاعدة كما في المصدر',a.methodology_rule_ar)}${item('المعالجة المنهجية',a.treatment_ar)}${list('مسار المعالجة',a.response_path_ar)}${cites?`<dt>الأدلة والمصادر</dt><dd><ul>${cites}</ul></dd>`:''}</dl><small>${esc(note)}${confidence} · البحث: ${esc(r.retrieval_mode)}${model}</small>`;
}
async function download(blob,name){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),30000);}
document.addEventListener('click',async e=>{
 const b=e.target.closest('button');if(!b)return;
 try{
 if(b.dataset.go){view=b.dataset.go;await render();}
 if(b.dataset.open)await openRecord(b.dataset.open);
 if(b.dataset.page){offset=Math.max(0,offset+(b.dataset.page==='next'?30:-30));await render();}
 if(b.dataset.source){const page='#page='+(b.dataset.pdfpage||1);const link=await api('/sources/'+b.dataset.source+'/pdf-url');
  if(link.url){window.open(link.url+page,'_blank','noopener');}
  else{const blob=await api('/sources/'+b.dataset.source+'/pdf',{blob:true});const url=URL.createObjectURL(blob);window.open(url+page,'_blank','noopener');setTimeout(()=>URL.revokeObjectURL(url),300000);}}
 if(b.dataset.chunks){const chunks=await api('/sources/'+b.dataset.chunks+'/chunks');$('#editor-content').innerHTML='<div class="modal-head"><h3>مقاطع المصدر</h3><button data-action="close">إغلاق</button></div><div class="card">'+chunks.map(c=>`<details><summary>صفحة ${c.page_number} · ${esc(c.section)}</summary><pre class="excerpt">${esc(c.text)}</pre></details>`).join('')+'</div>';$('#editor').showModal();}
 if(b.dataset.history){const history=await api('/records/'+b.dataset.history+'/history');$('#history').innerHTML=history.map(x=>`<details><summary>الإصدار ${x.snapshot.version} · ${esc(x.action)} · ${esc(x.actor)}</summary><pre class="json">${esc(JSON.stringify(x,null,2))}</pre></details>`).join('');}
 const action=b.dataset.action;
 if(action==='close')$('#editor').close();
 if(action==='filter'){query=$('#search').value;status=$('#status-filter').value;offset=0;await render();}
 if(action==='duplicates'){b.disabled=true;const r=await api('/duplicates',{method:'POST'});notify('اكتمل فحص التكرار: '+r.mode+'؛ الاقتراحات محفوظة وتحتاج مراجعة.');}
 if(action==='families'){b.disabled=true;const r=await api('/families',{method:'POST'});notify('عائلات مرشحة جديدة: '+r.created.length);await render();}
 if(action==='refresh-index'){b.disabled=true;const r=await api('/embeddings/refresh',{method:'POST',body:{include_drafts:true}});notify('حُدّث فهرس البحث: '+r.embedded_fields+' حقلًا.');}
 if(action==='json-export')await download(await api('/export-json',{blob:true}),'manhaj-approved.json');
 }catch(err){notify(err.message);}finally{b.disabled=false;}
});
document.addEventListener('submit',async e=>{
 if(e.target.id==='login-form')return;
 e.preventDefault();const button=e.submitter;if(button)button.disabled=true;
 try{
 const id=e.target.id;
 if(id==='review-form'){
 const changes={};for(const key of ['title_ar','objection_text_ar','central_claim_ar','diagnostic_reason_ar','revealing_question_ar','treatment_ar','methodology_rule_ar','core_claim_ar','core_confusion_ar']){const el=$('#edit-'+key);if(el)changes[key]=el.value;}
 for(const key of ['subclaims_ar','response_path_ar'])changes[key]=$('#edit-'+key).value.split('\n').map(x=>x.trim()).filter(Boolean);
 changes.compared_entities_ar=$('#edit-compared_entities_ar').value.split('\n').filter(x=>x.trim()).map(x=>{const [a,b]=x.split('|');if(!a||!b)throw Error('اكتب طرفي المقارنة مفصولين بعلامة |');return {entity_a:a.trim(),entity_b:b.trim()};});
 changes.primary_pattern=$('#edit-pattern').value;changes.sub_patterns=[...$('#edit-subpatterns').selectedOptions].map(x=>x.value);
 if($('#edit-ruleids'))changes.methodology_rule_ids=[...$('#edit-ruleids').selectedOptions].map(x=>x.value);
 changes.duplicate_group_id=$('#edit-duplicate_group_id').value||null;changes.family_id=$('#edit-family_id').value||null;changes.similarity_type=$('#edit-similarity').value;
 await api('/records/'+currentRecord.id+'/review',{method:'POST',body:{expected_version:currentRecord.version,action:button.value,changes,notes:$('#edit-notes').value,source_verified:$('#verify-source').checked,page_verified:$('#verify-page').checked,diagnosis_verified:$('#verify-diagnosis').checked}});
 $('#editor').close();notify('حُفظت المراجعة مع سجل الإصدار.');await render();
 }
 if(id==='ingest-form'){const form=new FormData();form.append('file',$('#pdf-file').files[0]);form.append('title',$('#pdf-title').value);form.append('author',$('#pdf-author').value);form.append('profile',$('#pdf-profile').value);notify('يجري استخراج الصفحات. قد يستغرق ذلك عدة دقائق.');const r=await api('/ingest',{method:'POST',body:form});notify('سجلات مرشحة جديدة: '+r.candidate_count);await render();}
 if(id==='diagnose-form'){$('#diagnosis-result').innerHTML='<div class="banner" role="status">جارٍ تحليل البنية واسترجاع القواعد… قد يستغرق ذلك حتى 30 ثانية.</div>';const r=await api('/diagnose',{method:'POST',body:{text:$('#diagnose-text').value,include_drafts:$('#diagnose-drafts').checked}});$('#diagnosis-result').innerHTML=diagnosisHtml(r);}
 if(id==='research-form'){const r=await api('/research',{method:'POST',body:{topic:$('#research-topic').value,limit:Number($('#research-limit').value)}});notify('حالات مرشحة: '+r.record_ids.length+'؛ تعذر الوصول إلى '+r.errors.length+' مصدر.');await render();}
 if(id==='gate-form'){await api('/phase-two/enable',{method:'POST',body:{coverage_verified:$('#coverage-check').checked,notes:$('#coverage-notes').value}});notify('وُثّق اكتمال المرحلة الأولى.');}
 if(id==='benchmark-form'){const ids=s=>$(s).value.split(/[\n,،]/).map(x=>x.trim()).filter(Boolean);await api('/benchmark',{method:'POST',body:{test_ids:ids('#test-ids'),validation_ids:ids('#validation-ids')}});notify('حُفظ المعيار وفُصلت العائلات.');await render();}
 if(id==='export-form'){const blob=await api('/export/'+$('#manifest').value,{method:'POST',blob:true});await download(blob,'manhaj-training.jsonl');await render();}
 }catch(err){notify(err.message);if(e.target.id==='diagnose-form')$('#diagnosis-result').innerHTML='';}finally{if(button)button.disabled=false;}
});
init();
