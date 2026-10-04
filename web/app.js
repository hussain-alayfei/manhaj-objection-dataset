'use strict';
const $ = (s, root=document) => root.querySelector(s);
const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const titles = {overview:'نظرة عامة',sources:'المصادر',objections:'شبهات الكتاب',external:'شبهات من مصادر أخرى',rules:'القواعد المنهجية',families:'الشبهات المتشابهة',review:'المراجعة',evaluation:'التقييم',export:'تصدير البيانات'};
const statuses={approved:'معتمد',needs_review:'يحتاج مراجعة',draft:'مسودة',rejected:'مرفوض'};
// Plain-language names for the stored codes, for reviewers who are not technical.
const patternNames={'جمع بين مختلفين':'جمع بين مختلفين','تفريق بين متماثلين':'تفريق بين متماثلين',unknown:'لم يُحدَّد بعد',mixed_pattern:'نمط مركّب',multiple_claims:'أكثر من دعوى',insufficient_evidence:'المعطيات غير كافية',requires_human_review:'يحتاج نظر مختص'};
const patternName=p=>patternNames[p]||p;
const similarityNames={exact_duplicate:'مكررة حرفيًا',paraphrase:'الشبهة نفسها بصياغة أخرى',same_underlying_objection:'أصلها شبهة واحدة',same_pattern_different_objection:'النمط نفسه مع شبهة مختلفة',new_case:'حالة جديدة'};
const historyActions={create:'إنشاء',edit:'تعديل',approve:'اعتماد',reject:'رفض',reopen:'إعادة فتح',machine_proposal:'اقتراح آلي'};
let token=sessionStorage.getItem('manhaj-token')||'', view='overview', offset=0, currentRecord=null, taxonomy={}, query='', status=null, caps={};
const badge=s=>`<span class="pill ${s==='approved'?'':s==='rejected'?'rejected':'pending'}">${esc(statuses[s]||s)}</span>`;
let noticeTimer;
function notify(message){
 const n=$('#notice');clearTimeout(noticeTimer);n.classList.remove('leaving');n.textContent=message;n.hidden=false;
 noticeTimer=setTimeout(()=>{n.classList.add('leaving');noticeTimer=setTimeout(()=>{n.hidden=true;n.classList.remove('leaving');},260);},6500);
}
function closeEditor(){const d=$('#editor');if(!d.open)return;d.classList.add('closing');setTimeout(()=>{d.classList.remove('closing');d.close();},180);}

// GET responses are kept for 60 s in memory; any write clears them.
const cache=new Map(), CACHE_MS=60000;
function api(path, options={}){
 const get=!options.method||options.method==='GET';
 if(!get||options.blob)return request(path,options).then(r=>{if(!get)cache.clear();return r;});
 const hit=cache.get(path);
 if(hit&&Date.now()-hit.at<CACHE_MS)return hit.promise;
 const promise=request(path,options).catch(e=>{cache.delete(path);throw e;});
 cache.set(path,{at:Date.now(),promise});
 return promise;
}
async function request(path, options={}){
 const headers={Authorization:`Bearer ${token}`,...options.headers};
 if(options.body && !(options.body instanceof FormData)){headers['Content-Type']='application/json';options.body=JSON.stringify(options.body);}
 const response=await fetch('/api'+path,{...options,headers});
 if(!response.ok){let error;try{error=await response.json();}catch{error={detail:'تعذر إكمال الطلب'};}const failure=Error(typeof error.detail==='string'?error.detail:JSON.stringify(error.detail));failure.status=response.status;throw failure;}
 return options.blob?response.blob():response.json();
}
function title(name,subtitle,action=''){return `<div class="page-title"><div><h2>${esc(name)}</h2><p>${esc(subtitle)}</p></div>${action}</div>`;}
async function init(){
 if(titles[location.hash.slice(1)])view=location.hash.slice(1);
 if(!token)return;
 try{const me=await api('/me');taxonomy=me.taxonomy;caps=me.capabilities||{};$('#identity').textContent=me.reviewer_id+(caps.read_only?' (قراءة فقط)':'');$('#login').hidden=true;$('#content').hidden=false;await render();prefetch();}
 catch(e){if(e.status===401){sessionStorage.removeItem('manhaj-token');token='';}$('#login').hidden=false;$('#content').hidden=true;notify(e.status===401?'رمز الوصول غير صحيح.':'تعذر الاتصال بالخادم. أعد تحميل الصفحة بعد قليل.');}
}
$('#login-form').addEventListener('submit',e=>{e.preventDefault();token=$('#token').value.trim();sessionStorage.setItem('manhaj-token',token);$('#token').value='';init();});
$('#logout').addEventListener('click',()=>{sessionStorage.removeItem('manhaj-token');location.reload();});

// Each tab has its own address (#rules, #review…) so refresh, Back/Forward and shared links keep the place.
function go(next){if(!titles[next])next='overview';offset=0;query='';status=null;if(location.hash.slice(1)!==next){location.hash=next;return;}view=next;render().catch(e=>notify(e.message));}
$('#nav').addEventListener('click',e=>{const b=e.target.closest('[data-view]');if(b)go(b.dataset.view);});
window.addEventListener('hashchange',()=>{const next=location.hash.slice(1);if(titles[next]&&token){view=next;offset=0;query='';status=null;render().catch(e=>notify(e.message));}});
// On narrow screens the tabs scroll sideways: keep the active one centred without moving the page vertically.
function centerTab(b){const n=b.parentElement;if(n.scrollWidth<=n.clientWidth)return;const nr=n.getBoundingClientRect(),br=b.getBoundingClientRect();n.scrollBy({left:br.left-nr.left-(nr.width-br.width)/2});}
function recordsPath(name,start=0,q='',chosen=name==='review'?'needs_review':''){
 const kind=name==='rules'?'rule':name==='families'?'family':name==='review'?'':'objection';
 const phase=name==='external'?2:name==='objections'?1:'';
 const params=new URLSearchParams({limit:'30',offset:String(start),q});if(kind)params.set('kind',kind);if(phase)params.set('phase',phase);if(chosen)params.set('status',chosen);
 return '/records?'+params;
}
// After the first page appears, quietly load every tab's first page so switching tabs is instant.
function prefetch(){
 const run=()=>{for(const name of ['review','objections','rules','families','external'])api(recordsPath(name)).catch(()=>{});
  for(const path of ['/sources','/documents/dataset_manifests','/documents/evaluation_runs','/documents/training_exports','/records?kind=rule&limit=200'])api(path).catch(()=>{});};
 ('requestIdleCallback' in window)?requestIdleCallback(run,{timeout:1500}):setTimeout(run,600);
}
let renderSeq=0;
const stale=seq=>seq!==renderSeq; // a slower response from a previous tab must not overwrite the current one

async function render(){
 if(!token)return;
 renderSeq++;
 const seq=renderSeq;let done=false;$('#content').setAttribute('aria-busy','true');
 // Dim the old page only if the new one takes noticeably long (never after it has already appeared).
 setTimeout(()=>{if(!done&&!stale(seq))$('#content').classList.add('loading');},120);
 $('#breadcrumb').textContent=titles[view];
 document.querySelectorAll('[data-view]').forEach(b=>{const on=b.dataset.view===view;b.classList.toggle('active',on);if(on){b.setAttribute('aria-current','page');centerTab(b);}else b.removeAttribute('aria-current');});
 try{
  if(view==='overview')return await overview();
  if(view==='sources')return await sourcesView();
  if(view==='evaluation')return await evaluationView();
  if(view==='export')return await exportView();
  return await recordsView();
 }finally{done=true;if(!stale(seq)){$('#content').classList.remove('loading');$('#content').removeAttribute('aria-busy');}}
}
const page=r=>r.source?.page_number?'صفحة '+r.source.page_number:'';
const where=r=>[r.source?.source_name,page(r)].filter(Boolean).join('، ');
async function overview(){
 const seq=renderSeq;
 const [s,records]=await Promise.all([api('/summary'),api('/records?kind=objection&status=needs_review&limit=5')]);
 if(stale(seq))return;
 const figures=[['المصادر',s.sources,'كتاب وليد'],['الشبهات',s.objections,'استُخرجت من نص الكتاب'],['القواعد المنهجية',s.rules,'تُراجع قبل استخدامها'],['بانتظار المراجعة',s.pending,`${s.approved.toLocaleString('ar')} سجل معتمد`]];
 $('#content').innerHTML=title('نظرة عامة','ما ينتظر المراجعة في المشروع الآن.')+
 `<div class="metrics">${figures.map(([label,n,note])=>`<div class="metric"><div class="label">${label}</div><strong>${n.toLocaleString('ar')}</strong><small>${note}</small></div>`).join('')}</div>
 <div class="hero"><h3>كيف تُحلَّل الشبهة؟</h3><p>تمر كل شبهة بخمس خطوات، ولا يُعتمد شيء قبل أن يراجعه مختص.</p><ol class="steps"><li>تحديد ما يدّعيه المعترض</li><li>تحديد الطرفين المقارَن بينهما</li><li>تحديد موضع الإشكال</li><li>ربطه بقاعدة من الكتاب</li><li>صياغة طريقة الرد</li></ol></div>
 <div class="two-col"><section class="card"><div class="card-head"><h3>بانتظار المراجعة</h3><button class="quiet" data-go="review">عرض الكل</button></div>${records.items.map(r=>`<div class="row"><div class="text"><h4>${esc(r.title_ar)}</h4><p>${esc(where(r))}</p></div><button data-open="${esc(r.id)}">مراجعة</button></div>`).join('')||'<div class="empty">لا توجد حالات بانتظار المراجعة.</div>'}</section>
 <section class="guarantees"><h3>كيف نضمن صحة البيانات</h3><div class="guarantee"><b>النص من الكتاب نفسه</b><p>كل مقتطف محفوظ برقم صفحته وموضعه في النص.</p></div><div class="guarantee"><b>التحليل اقتراح</b><p>يقترح النظام التشخيص، ويمتنع عنه إذا لم تكفِ الأدلة.</p></div><div class="guarantee"><b>الاعتماد بيد المختص</b><p>لا يُستخدم أي سجل في التقييم أو التدريب قبل أن يعتمده مراجع.</p></div></section></div>
 <section class="card spaced"><h3>حلّل شبهة</h3><p class="muted">اكتب الشبهة كما سمعتها أو قرأتها. سيقترح النظام تشخيصًا مستندًا إلى قواعد الكتاب، والنتيجة اقتراح يراجعه مختص.</p><form id="diagnose-form"><label for="diagnose-text">نص الشبهة</label><textarea id="diagnose-text" required maxlength="12000" placeholder="مثال: لماذا تقولون إن الحكم واحد مع أن الحالتين مختلفتان؟"></textarea><label class="check"><input id="diagnose-drafts" type="checkbox">استخدم أيضًا القواعد التي لم تُراجع بعد (تُعلَّم النتيجة «مسودة»)</label><button class="primary spaced">حلّل الشبهة</button>${caps.semantic&&!caps.read_only?' <button type="button" class="spaced" data-action="refresh-index">تحديث فهرس البحث</button>':''}</form><div id="diagnosis-result" class="spaced" aria-live="polite"></div></section>`;
}
async function recordsView(){
 const seq=renderSeq;
 const chosen=status===null?(view==='review'?'needs_review':''):status;
 const data=await api(recordsPath(view,offset,query,chosen));
 if(!data.items.length&&offset>0&&offset>=data.total){offset=Math.max(0,Math.ceil(data.total/30)*30-30);return render();}
 let extra='';
 if(view==='external')extra=!caps.heavy_jobs?'<div class="banner">جمع الشبهات من مصادر أخرى يتم من سطر الأوامر، وكل نتيجة تدخل قائمة المراجعة.</div>':`<div class="banner">يبدأ جمع الشبهات من مصادر أخرى بعد إنهاء مراجعة الكتاب كاملًا، وكل نتيجة تدخل قائمة المراجعة.</div><details class="card spaced"><summary>البحث في المصادر المسموح بها</summary><form id="research-form"><label for="research-topic">الموضوع</label><input id="research-topic" required><label for="research-limit">أقصى عدد من النتائج</label><input id="research-limit" type="number" min="1" max="50" value="5"><button class="primary spaced">ابحث</button></form><form id="gate-form"><label class="check"><input id="coverage-check" type="checkbox" required>أشهد بأن مراجعة جميع شبهات الكتاب وقواعده اكتملت.</label><label for="coverage-notes">ملاحظات المراجعة</label><textarea id="coverage-notes" required></textarea><button class="spaced">توثيق اكتمال مراجعة الكتاب</button></form></details>`;
 const actions=!caps.heavy_jobs?'':view==='families'?'<button data-action="families">اقترح مجموعات متشابهة</button>':view==='objections'?'<button data-action="duplicates">ابحث عن المكرر</button>':'';
 if(stale(seq))return;
 $('#content').innerHTML=title(titles[view],`${data.total.toLocaleString('ar')} سجل`,actions)+extra+`<div class="toolbar spaced"><input id="search" aria-label="بحث" placeholder="ابحث في العنوان أو النص…" value="${esc(query)}"><select id="status-filter" aria-label="حالة المراجعة"><option value="" ${chosen===''?'selected':''}>جميع الحالات</option>${Object.entries(statuses).map(([k,v])=>`<option value="${k}" ${chosen===k?'selected':''}>${v}</option>`).join('')}</select><button data-action="filter">بحث</button></div><section class="card"><div class="table-wrap"><table><thead><tr><th>العنوان</th><th>التشخيص</th><th>المصدر</th><th>الحالة</th><th><span class="sr-only">إجراء</span></th></tr></thead><tbody>${data.items.map(r=>`<tr><td>${esc(r.title_ar)}<small dir="ltr">${esc(r.id)}</small></td><td>${esc(patternName(r.primary_pattern))}<small>${esc(r.sub_patterns.join('، '))}</small></td><td>${esc(r.source?.source_name||'مجموعة مقترحة')}<small>${esc(page(r))||'—'}</small></td><td>${badge(r.review_status)}</td><td><button data-open="${esc(r.id)}">فتح</button></td></tr>`).join('')}</tbody></table>${data.items.length?'':'<div class="empty">لا توجد سجلات مطابقة.</div>'}</div><div class="pagination"><span>${data.total?offset+1:0}–${Math.min(offset+30,data.total)} من ${data.total}</span><div><button data-page="prev" ${offset===0?'disabled':''}>السابق</button> <button data-page="next" ${offset+30>=data.total?'disabled':''}>التالي</button></div></div></section>`;
}
async function sourcesView(){
 const seq=renderSeq;
 const sources=await api('/sources');
 if(stale(seq))return;
 $('#content').innerHTML=title('المصادر','الكتب التي استُخرجت منها الشبهات والقواعد.')+`<div class="list-stack">${sources.map(s=>`<article class="card source-card"><img class="book-cover" src="/static/img/book-cover.webp" alt="" width="72" height="96"><div class="text"><h3>${esc(s.source_name)}</h3><p>${esc(s.actual_title||'')}${s.author?' — '+esc(s.author):''}</p><p>${s.page_count?s.page_count+' صفحة':''}</p><small dir="ltr">${esc(s.id)}</small></div><button data-source="${esc(s.id)}">افتح الكتاب</button><button data-chunks="${esc(s.id)}">النص مقسّمًا</button></article>`).join('')}</div>${!caps.heavy_jobs?'<div class="banner spaced">إضافة كتاب جديد تتم من سطر الأوامر (python scripts/ingest_book.py).</div>':`<details class="card spaced"><summary>إضافة كتاب PDF</summary><form id="ingest-form"><label for="pdf-title">اسم الكتاب</label><input id="pdf-title" value="كتاب وليد" required><label for="pdf-author">المؤلف كما يظهر في الكتاب</label><input id="pdf-author"><label for="pdf-profile">طريقة ترتيب النص</label><select id="pdf-profile"><option value="standard">عادية</option><option value="rtl_visual">حروف معكوسة الترتيب (مثل الكتاب الحالي)</option></select><label for="pdf-file">ملف PDF</label><input id="pdf-file" type="file" accept="application/pdf" required><button class="primary spaced">استخراج إلى قائمة المراجعة</button></form></details>`}`;
}
async function evaluationView(){
 const seq=renderSeq;
 const [manifests,runs]=await Promise.all([api('/documents/dataset_manifests'),api('/documents/evaluation_runs')]);
 if(stale(seq))return;
 $('#content').innerHTML=title('التقييم','قياس جودة التحليل على حالات معتمدة لم تُستخدم في التدريب.')+`<div class="banner">لا توجد نتائج بعد. تظهر هنا بعد اعتماد الحالات وإنشاء مجموعة اختبار.</div><div class="two-col"><section class="card"><h3>إنشاء مجموعة اختبار</h3><form id="benchmark-form"><label for="test-ids">أرقام حالات الاختبار المعتمدة (سطر لكل حالة)</label><textarea id="test-ids" required dir="ltr"></textarea><label for="validation-ids">أرقام حالات التحقق (اختياري)</label><textarea id="validation-ids" dir="ltr"></textarea><button class="primary spaced">حفظ المجموعة</button></form></section><section class="card"><h3>المجموعات المحفوظة</h3>${manifests.map(m=>`<div class="row"><div><small dir="ltr">${esc(m.id)}</small><p>تدريب ${m.payload.training_ids.length}، تحقق ${m.payload.validation_ids.length}، اختبار ${m.payload.test_ids.length}</p></div></div>`).join('')||'<div class="empty">تُنشأ بعد اعتماد الحالات.</div>'}</section></div><section class="card spaced"><h3>نتائج التقييم</h3>${runs.map(r=>`<details><summary>${esc(r.id)}</summary><pre class="json">${esc(JSON.stringify(r.payload.metrics,null,2))}</pre></details>`).join('')||'<div class="empty">لم يُجرَ تقييم بعد.</div>'}</section>`;
}
async function exportView(){
 const seq=renderSeq;
 const [manifests,exports]=await Promise.all([api('/documents/dataset_manifests'),api('/documents/training_exports')]);
 if(stale(seq))return;
 $('#content').innerHTML=title('تصدير البيانات','تُصدَّر الحالات المعتمدة فقط، وتُستبعد حالات الاختبار.')+`<div class="two-col"><section class="card"><h3>ملف التدريب</h3><form id="export-form"><label for="manifest">مجموعة البيانات</label><select id="manifest" required><option value="">اختر مجموعة</option>${manifests.map(m=>`<option value="${esc(m.id)}">${esc(m.id)} (${m.payload.training_ids.length} حالة تدريب)</option>`).join('')}</select><button class="primary spaced">تنزيل ملف التدريب</button></form><button data-action="json-export" class="spaced">تنزيل كل السجلات المعتمدة</button></section><section class="card"><h3>عمليات التصدير السابقة</h3>${exports.map(x=>`<div class="row"><div><small>${esc(new Date(x.payload.at).toLocaleString('ar'))}</small><p>${x.payload.records.length} حالة</p></div></div>`).join('')||'<div class="empty">لا توجد عمليات تصدير.</div>'}</section></div>`;
}
function field(id,label,value,rows=false){return `<label for="edit-${id}">${label}</label>${rows?`<textarea id="edit-${id}">${esc(value)}</textarea>`:`<input id="edit-${id}" value="${esc(value)}">`}`;}
async function openRecord(id){
 const [r,rules]=await Promise.all([api('/records/'+id),api('/records?kind=rule&limit=200')]);currentRecord=r;
 const patterns=[...Object.keys(taxonomy),'mixed_pattern','multiple_claims','unknown','insufficient_evidence','requires_human_review'];
 const kindName=r.kind==='rule'?'القاعدة':r.kind==='family'?'مجموعة الشبهات':'الشبهة';
 $('#editor-content').innerHTML=`<div class="modal-head"><div><small dir="ltr">${esc(r.id)} · v${r.version}</small><h3 id="editor-title">مراجعة ${kindName} ${badge(r.review_status)}</h3></div><button data-action="close">إغلاق</button></div><div class="modal-grid"><section><div class="layer">١. نص الكتاب</div><div class="evidence"><h3>${esc(r.source?.source_name||'مجموعة مقترحة')}</h3><div class="source-meta"><span>${esc(r.source?.author||'')}</span><span>${esc(page(r))}</span><span>${esc(r.source?.section||'')}</span></div>${r.source?.source_type==='book'?`<button data-source="${esc(r.source.source_id)}" data-pdfpage="${r.source.page_number}">افتح الصفحة في الكتاب</button>`:''}<div class="excerpt">${esc(r.source?.source_excerpt||r.common_variants_ar.join('\n\n'))}</div></div>${r.kind==='objection'?`<h3 class="spaced">نص الشبهة المختار</h3><p>${esc(r.objection_text_ar||'—')}</p>`:''}<details class="spaced"><summary>اقتراح النظام المحفوظ</summary><pre class="json">${esc(JSON.stringify(r.ai_analysis,null,2))}</pre></details><button class="quiet spaced" data-history="${esc(r.id)}">سجل التعديلات</button><div id="history"></div></section><section><div class="layer">٢. تحليل المراجع</div><form id="review-form">${field('title_ar','العنوان',r.title_ar)}${r.kind==='objection'?field('objection_text_ar','نص الشبهة (اختر العبارة من نص الكتاب)',r.objection_text_ar,true):''}${field('central_claim_ar','ما يدّعيه المعترض',r.central_claim_ar,true)}${field('subclaims_ar','تفاصيل الدعوى (سطر لكل نقطة)',r.subclaims_ar.join('\n'),true)}${field('compared_entities_ar','طرفا المقارنة (كل سطر: الطرف الأول | الطرف الثاني)',r.compared_entities_ar.map(x=>x.entity_a+' | '+x.entity_b).join('\n'),true)}<div class="fields-two"><div><label for="edit-pattern">التشخيص</label><select id="edit-pattern">${patterns.map(p=>`<option value="${esc(p)}" ${p===r.primary_pattern?'selected':''}>${esc(patternName(p))}</option>`).join('')}</select></div><div><label for="edit-subpatterns">تفصيل التشخيص</label><select id="edit-subpatterns" multiple size="4">${Object.values(taxonomy).flat().map(p=>`<option ${r.sub_patterns.includes(p)?'selected':''}>${esc(p)}</option>`).join('')}</select></div></div>${field('diagnostic_reason_ar','سبب التشخيص',r.diagnostic_reason_ar,true)}${field('revealing_question_ar','سؤال يكشف الإشكال',r.revealing_question_ar,true)}${r.kind==='rule'?field('methodology_rule_ar','نص القاعدة كما في الكتاب (انسخه حرفيًا من المقتطف)',r.methodology_rule_ar,true):`<label for="edit-ruleids">القواعد المرتبطة (الاعتماد يتطلب قواعد معتمدة)</label><select id="edit-ruleids" multiple size="4">${rules.items.filter(x=>x.review_status!=='rejected'||r.methodology_rule_ids.includes(x.id)).map(x=>`<option value="${esc(x.id)}" ${r.methodology_rule_ids.includes(x.id)?'selected':''}>${esc(x.title_ar)}${x.review_status==='approved'?'':' ('+esc(statuses[x.review_status]||x.review_status)+')'}</option>`).join('')}</select>`}${field('treatment_ar','طريقة المعالجة',r.treatment_ar,true)}${field('response_path_ar','خطوات الرد (سطر لكل خطوة)',r.response_path_ar.join('\n'),true)}${r.kind==='family'?field('core_claim_ar','الدعوى المشتركة',r.core_claim_ar,true)+field('core_confusion_ar','موضع الالتباس المشترك',r.core_confusion_ar,true):''}<details><summary>التكرار والتشابه</summary>${field('duplicate_group_id','رقم مجموعة التكرار',r.duplicate_group_id||'')}${field('family_id','رقم مجموعة التشابه',r.family_id||'')}<label for="edit-similarity">نوع التشابه</label><select id="edit-similarity">${Object.entries(similarityNames).map(([x,name])=>`<option value="${x}" ${x===r.similarity_type?'selected':''}>${name}</option>`).join('')}</select></details>${field('notes','ملاحظات المراجع',r.reviewer_notes,true)}<div class="layer spaced">٣. الاعتماد</div><label class="check"><input id="verify-source" type="checkbox">تحققت من أن المقتطف مطابق للكتاب ومنسوب لقائله الصحيح.</label><label class="check"><input id="verify-page" type="checkbox">تحققت من رقم الصفحة في الكتاب.</label><label class="check"><input id="verify-diagnosis" type="checkbox">راجعت الدعوى والتشخيص وحدود الدليل.</label><div class="actions"><button class="primary" name="action" value="approve">اعتماد</button><button name="action" value="edit">حفظ دون اعتماد</button><button class="danger" name="action" value="reject">رفض</button></div></form></section></div>`;
 $('#editor').showModal();
}
const abstentions={no_approved_methodology:'لا توجد قاعدة معتمدة تناسب هذه الشبهة بعد، فلم يصنّفها النظام. يمكنك تفعيل خيار القواعد التي لم تُراجع.',model_not_configured:'خدمة التحليل غير مفعّلة.',model_or_grounding_validation_failed:'لم يستند اقتراح النظام إلى قواعد الكتاب، فاستُبعد.',retrieval_unavailable:'تعذر البحث في الكتاب الآن. حاول بعد قليل.',safety_gate:'أوقف النظام نتيجة خرجت عن حدود التشخيص.'};
function diagnosisHtml(r){
 const a=r.analysis,draft=r.mode==='draft',item=(label,value)=>value&&String(value).trim()?`<dt>${label}</dt><dd>${esc(value)}</dd>`:'';
 const list=(label,values)=>values&&values.length?`<dt>${label}</dt><dd><ol>${values.map(x=>`<li>${esc(x)}</li>`).join('')}</ol></dd>`:'';
 const cites=r.source_evidence.map(c=>`<li>${esc(c.source?.source_name||'')}، صفحة ${c.source?.page_number??'—'} ${badge(c.review_status||'approved')}</li>`).join('');
 const note=r.abstention_reason?(abstentions[r.abstention_reason]||'لم يصنّف النظام هذه الشبهة.'):'اقتراح مستند إلى قواعد الكتاب، يحتاج مراجعة مختص.';
 const confidence=a.confidence!=null&&!r.abstention_reason?` درجة الثقة ${Math.round(a.confidence*100)}٪.`:'';
 return `<div class="verdict">${draft?'<span class="pill draft">مسودة</span>':''}<strong>${esc(patternName(a.primary_pattern))}</strong><span class="pill pending">يحتاج مراجعة مختص</span></div><dl class="diagnosis">${item('ما يدّعيه المعترض',a.central_claim_ar)}${list('تفاصيل الدعوى',a.subclaims_ar)}${list('طرفا المقارنة',a.compared_entities_ar.map(x=>x.entity_a+' ⟷ '+x.entity_b))}${list('تفصيل التشخيص',a.sub_patterns)}${item('سبب التشخيص',a.diagnostic_reason_ar)}${item('سؤال يكشف الإشكال',a.revealing_question_ar)}${item('القاعدة من الكتاب',a.methodology_rule_ar)}${item('طريقة المعالجة',a.treatment_ar)}${list('خطوات الرد',a.response_path_ar)}${cites?`<dt>المصادر</dt><dd><ul>${cites}</ul></dd>`:''}</dl><small class="meta">${esc(note)}${confidence}</small>`;
}
async function download(blob,name){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),30000);}
document.addEventListener('click',async e=>{
 const b=e.target.closest('button');if(!b)return;
 try{
 if(b.dataset.go)go(b.dataset.go);
 if(b.dataset.open)await openRecord(b.dataset.open);
 if(b.dataset.page){offset=Math.max(0,offset+(b.dataset.page==='next'?30:-30));await render();}
 if(b.dataset.source){const target='#page='+(b.dataset.pdfpage||1);const tab=window.open('','_blank');if(tab)tab.opener=null;
  try{const link=await api('/sources/'+b.dataset.source+'/pdf-url');let url=link.url;
  if(!url){url=URL.createObjectURL(await api('/sources/'+b.dataset.source+'/pdf',{blob:true}));setTimeout(()=>URL.revokeObjectURL(url),300000);}
  if(tab)tab.location.href=url+target;else notify('اسمح بالنوافذ المنبثقة لهذا الموقع لفتح الكتاب.');}catch(err){tab?.close();throw err;}}
 if(b.dataset.chunks){const chunks=await api('/sources/'+b.dataset.chunks+'/chunks');$('#editor-content').innerHTML='<div class="modal-head"><h3 id="editor-title">نص الكتاب مقسّمًا</h3><button data-action="close">إغلاق</button></div><div class="card">'+chunks.map(c=>`<details><summary>صفحة ${c.page_number}: ${esc(c.section)}</summary><pre class="excerpt">${esc(c.text)}</pre></details>`).join('')+'</div>';$('#editor').showModal();}
 if(b.dataset.history){const history=await api('/records/'+b.dataset.history+'/history');$('#history').innerHTML=history.map(x=>`<details><summary>الإصدار ${x.snapshot.version}: ${esc(historyActions[x.action]||x.action)} (${esc(x.actor)})</summary><pre class="json">${esc(JSON.stringify(x,null,2))}</pre></details>`).join('');}
 const action=b.dataset.action;
 if(action==='close')closeEditor();
 if(action==='filter'){query=$('#search').value;status=$('#status-filter').value;offset=0;await render();}
 if(action==='duplicates'){b.disabled=true;await api('/duplicates',{method:'POST'});notify('اكتمل البحث عن المكرر، والاقتراحات تنتظر المراجعة.');}
 if(action==='families'){b.disabled=true;const r=await api('/families',{method:'POST'});notify('مجموعات مقترحة جديدة: '+r.created.length);await render();}
 if(action==='refresh-index'){b.disabled=true;await api('/embeddings/refresh',{method:'POST',body:{include_drafts:true}});notify('حُدّث فهرس البحث.');}
 if(action==='json-export')await download(await api('/export-json',{blob:true}),'manhaj-approved.json');
 }catch(err){notify(err.message);}finally{b.disabled=false;}
});
document.addEventListener('submit',async e=>{
 if(e.target.id==='login-form')return;
 e.preventDefault();const button=e.submitter;if(e.target.id==='review-form'&&!button?.value)return;if(button)button.disabled=true;
 try{
 const id=e.target.id;
 if(id==='review-form'){
 const changes={};for(const key of ['title_ar','objection_text_ar','central_claim_ar','diagnostic_reason_ar','revealing_question_ar','treatment_ar','methodology_rule_ar','core_claim_ar','core_confusion_ar']){const el=$('#edit-'+key);if(el)changes[key]=el.value;}
 for(const key of ['subclaims_ar','response_path_ar'])changes[key]=$('#edit-'+key).value.split('\n').map(x=>x.trim()).filter(Boolean);
 changes.compared_entities_ar=$('#edit-compared_entities_ar').value.split('\n').filter(x=>x.trim()).map(x=>{const [a,b]=x.split('|');if(!a||!b)throw Error('اكتب طرفي المقارنة مفصولين بعلامة |');return {entity_a:a.trim(),entity_b:b.trim()};});
 changes.primary_pattern=$('#edit-pattern').value;changes.sub_patterns=[...$('#edit-subpatterns').selectedOptions].map(x=>x.value);
 if($('#edit-ruleids')){const ids=[...$('#edit-ruleids').selectedOptions].map(x=>x.value);if(ids.join()!==currentRecord.methodology_rule_ids.join())changes.methodology_rule_ids=ids;}
 changes.duplicate_group_id=$('#edit-duplicate_group_id').value||null;changes.family_id=$('#edit-family_id').value||null;changes.similarity_type=$('#edit-similarity').value;
 await api('/records/'+currentRecord.id+'/review',{method:'POST',body:{expected_version:currentRecord.version,action:button.value,changes,notes:$('#edit-notes').value,source_verified:$('#verify-source').checked,page_verified:$('#verify-page').checked,diagnosis_verified:$('#verify-diagnosis').checked}});
 closeEditor();notify(button.value==='approve'?'اعتُمد السجل.':button.value==='reject'?'رُفض السجل.':'حُفظت التعديلات.');await render();
 }
 if(id==='ingest-form'){const form=new FormData();form.append('file',$('#pdf-file').files[0]);form.append('title',$('#pdf-title').value);form.append('author',$('#pdf-author').value);form.append('profile',$('#pdf-profile').value);notify('يجري استخراج الصفحات، وقد يستغرق ذلك عدة دقائق.');const r=await api('/ingest',{method:'POST',body:form});notify('سجلات جديدة بانتظار المراجعة: '+r.candidate_count);await render();}
 if(id==='diagnose-form'){$('#diagnosis-result').innerHTML='<div class="banner" role="status">جارٍ تحليل الشبهة والبحث في قواعد الكتاب، وقد يستغرق ذلك حتى 30 ثانية.</div>';const r=await api('/diagnose',{method:'POST',body:{text:$('#diagnose-text').value,include_drafts:$('#diagnose-drafts').checked}});$('#diagnosis-result').innerHTML=diagnosisHtml(r);}
 if(id==='research-form'){const r=await api('/research',{method:'POST',body:{topic:$('#research-topic').value,limit:Number($('#research-limit').value)}});notify('حالات جديدة: '+r.record_ids.length+'، ومصادر تعذر الوصول إليها: '+r.errors.length);await render();}
 if(id==='gate-form'){await api('/phase-two/enable',{method:'POST',body:{coverage_verified:$('#coverage-check').checked,notes:$('#coverage-notes').value}});notify('وُثّق اكتمال مراجعة الكتاب.');}
 if(id==='benchmark-form'){const ids=s=>$(s).value.split(/[\n,،]/).map(x=>x.trim()).filter(Boolean);await api('/benchmark',{method:'POST',body:{test_ids:ids('#test-ids'),validation_ids:ids('#validation-ids')}});notify('حُفظت مجموعة الاختبار.');await render();}
 if(id==='export-form'){const blob=await api('/export/'+$('#manifest').value,{method:'POST',blob:true});await download(blob,'manhaj-training.jsonl');await render();}
 }catch(err){notify(err.message);if(e.target.id==='diagnose-form')$('#diagnosis-result').innerHTML='';}finally{if(button)button.disabled=false;}
});
// Enter in the search box searches; Enter in a one-line review field must not trigger "approve".
document.addEventListener('keydown',e=>{if(e.key!=='Enter')return;if(e.target.id==='search'){e.preventDefault();$('[data-action="filter"]')?.click();}else if(e.target.matches('#review-form input:not([type=checkbox])'))e.preventDefault();});
init();
