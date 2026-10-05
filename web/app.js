'use strict';
const $ = (s, root=document) => root.querySelector(s);
const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = n => Number(n||0).toLocaleString('en');
const titles = {overview:'نظرة عامة',analyze:'حلّل شبهة',sources:'المصادر',objections:'شبهات الكتاب',external:'شبهات من مصادر أخرى',rules:'القواعد المنهجية',families:'الشبهات المتشابهة',review:'المراجعة',evaluation:'التقييم',export:'تصدير البيانات'};
const statuses={approved:'معتمد',needs_review:'يحتاج مراجعة',draft:'مسودة',rejected:'مرفوض'};
// Plain-language names for the stored codes, for reviewers who are not technical.
const patternNames={'جمع بين مختلفين':'جمع بين مختلفين','تفريق بين متماثلين':'تفريق بين متماثلين',unknown:'لم يُحدَّد بعد',mixed_pattern:'نمط مركّب',multiple_claims:'أكثر من دعوى',insufficient_evidence:'المعطيات غير كافية',requires_human_review:'يحتاج نظر مختص'};
const patternName=p=>patternNames[p]||p;
const subNames={'أصل ≠ وصف':'الخلط بين الأصل والوصف','فعل ≠ فاعل':'الخلط بين الفعل والفاعل'};
const subName=p=>subNames[p]||p;
const similarityNames={exact_duplicate:'مكررة حرفيًا',paraphrase:'الشبهة نفسها بصياغة أخرى',same_underlying_objection:'أصلها شبهة واحدة',same_pattern_different_objection:'النمط نفسه مع شبهة مختلفة',new_case:'حالة جديدة'};
const historyActions={create:'إنشاء',edit:'تعديل',approve:'اعتماد',reject:'رفض',reopen:'إعادة فتح',machine_proposal:'اقتراح آلي'};
// The session token is remembered on this device until the reviewer signs out.
const remember={get(){try{return localStorage.getItem('manhaj-session')||'';}catch{return '';}},set(v){try{v?localStorage.setItem('manhaj-session',v):localStorage.removeItem('manhaj-session');}catch{}}};
try{sessionStorage.removeItem('manhaj-token');}catch{}
let token=remember.get(), ready=false, view='overview', offset=0, currentRecord=null, taxonomy={}, query='', status=null, caps={};
const badge=s=>`<span class="pill ${s==='approved'?'':s==='rejected'?'rejected':'pending'}">${esc(statuses[s]||s)}</span>`;
let noticeTimer;
// A notification banner in the manner of Apple's: frosted material, the app's icon and name, the message.
// It lives in the browser's top layer (popover), so it always shows above an open window.
function notify(message,kind='success'){
 const n=$('#notice');clearTimeout(noticeTimer);
 n.className='notice '+kind;n.setAttribute('role',kind==='error'?'alert':'status');
 n.innerHTML=`<img class="notice-app" src="/static/img/emblem.webp" alt="" width="34" height="34"><div class="notice-text"><div class="notice-meta"><b>مَنْهَج</b><span>الآن</span></div><p></p></div><button type="button" class="notice-close" aria-label="إغلاق الرسالة"><svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="2.4" d="M18 6 6 18M6 6l12 12"/></svg></button>`;
 n.querySelector('p').textContent=message;
 if(n.showPopover){try{n.hidePopover();}catch{}n.showPopover();}else{(document.querySelector('dialog[open]')||document.body).appendChild(n);n.hidden=false;}
 noticeTimer=setTimeout(hideNotice,kind==='error'?8000:4500);
}
// swipe the banner up to dismiss it, as on a phone
let noticeY=null;
document.addEventListener('pointerdown',e=>{if(e.target.closest('#notice')&&!e.target.closest('.notice-close'))noticeY=e.clientY;});
document.addEventListener('pointerup',e=>{if(noticeY!==null&&noticeY-e.clientY>24)hideNotice();noticeY=null;});
function hideNotice(){const n=$('#notice');clearTimeout(noticeTimer);n.classList.add('leaving');noticeTimer=setTimeout(()=>{if(n.hidePopover){try{n.hidePopover();}catch{}}else n.hidden=true;n.classList.remove('leaving');},220);}
document.addEventListener('click',e=>{if(e.target.closest('.notice-close'))hideNotice();});
// The book's PDF extraction mirrored brackets and left spaces before commas: show the text as it is printed.
// (Stored evidence is untouched; matching on the server ignores brackets and punctuation spacing.)
function ar(value){
 let t=String(value??'');
 for(const [o,c] of [['{','}'],['(',')'],['[',']']]){const i=t.indexOf(o),j=t.indexOf(c);if(j!==-1&&(i===-1||j<i))t=[...t].map(ch=>ch===o?c:ch===c?o:ch).join('');}
 t=t.replace(/\{\s*/g,'﴿').replace(/\s*\}/g,'﴾').replace(/"\s*([^"\n]{1,400}?)\s*"/g,'«$1»');
 t=t.replace(/([^\s(\[﴿«"])([(\[﴿«])/g,'$1 $2').replace(/([)\]﴾»])(?=[؀-ۿ0-9])/g,'$1 ');
 t=t.replace(/([(\[«﴿])\s+/g,'$1').replace(/\s+([)\]»﴾])/g,'$1');
 t=t.replace(/[ \t]+([،؛:.!؟,])/g,'$1').replace(/([،؛])(?=[^\s\d])/g,'$1 ');
 return t;
}
const loaderHtml=text=>`<div class="loader" role="status"><span class="loader-mark" aria-hidden="true"></span><span>${esc(text)}</span></div>`;
function closeDialog(d){if(!d.open)return;d.classList.add('closing');setTimeout(()=>{d.classList.remove('closing');d.close();},180);}

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
 const headers={...(token?{Authorization:`Bearer ${token}`}:{}),...options.headers};
 if(options.body && !(options.body instanceof FormData)){headers['Content-Type']='application/json';options.body=JSON.stringify(options.body);}
 const response=await fetch('/api'+path,{...options,headers});
 if(!response.ok){let error;try{error=await response.json();}catch{error={detail:'تعذر إكمال الطلب'};}const failure=Error(typeof error.detail==='string'?error.detail:Array.isArray(error.detail)?'تحقق من البيانات المدخلة.':'تعذر إكمال الطلب');failure.status=response.status;if(response.status===401&&ready&&!path.startsWith('/auth/'))signedOut('انتهت الجلسة. سجّل الدخول من جديد.');throw failure;}
 return options.blob?response.blob():response.json();
}
function title(name,subtitle,action=''){return `<div class="page-title"><div><h2>${esc(name)}</h2><p>${esc(subtitle)}</p></div>${action}</div>`;}
// Two faces: the public introduction for guests, the reviewing desk once signed in.
function setMode(mode){document.body.dataset.mode=mode;if(mode==='landing')document.title='مَنْهَج | مراجعة الشبهات';}
async function init(){
 if(titles[location.hash.slice(1)])view=location.hash.slice(1);
 if(!token){setMode('landing');return;}
 setMode('app');
 try{const me=await api('/me');ready=true;taxonomy=me.taxonomy;caps=me.capabilities||{};showAccount(me);await render();prefetch();}
 catch(e){ready=false;if(e.status===401){signedOut(token?'انتهت الجلسة. سجّل الدخول من جديد.':'');return;}notify('تعذر الاتصال بالخادم. أعد تحميل الصفحة بعد قليل.','error');}
}
function signedOut(message){token='';remember.set('');ready=false;cache.clear();$('#content').innerHTML='';delete $('#content').dataset.view;document.querySelectorAll('dialog[open]').forEach(d=>d.close());setMode('landing');if(message)notify(message,'error');}
// ---------- Account: chip, menu, profile, sign out ----------
let me_={};
const initial=name=>(String(name||'؟').trim()[0]||'؟');
function showAccount(me){
 me_=me;const name=me.name||me.reviewer_id;
 document.querySelectorAll('[data-account-name]').forEach(x=>x.textContent=name+(caps.read_only?' (قراءة فقط)':''));
 document.querySelectorAll('[data-account-initial]').forEach(x=>x.textContent=initial(name));
 document.querySelectorAll('[data-account-sub]').forEach(x=>x.textContent=me.role==='admin'?'مسؤول المشروع':me.role==='visitor'?'زائر':'مراجع');
 $('#account-button').hidden=me.role==='visitor';
}
function openMenu(anchor){
 const m=$('#account-menu');if(m.matches(':popover-open')){m.hidePopover();return;}
 m.showPopover();const r=anchor.getBoundingClientRect(),w=m.offsetWidth,h=m.offsetHeight;
 const top=r.top-h-8>8?r.top-h-8:r.bottom+8; // above the chip in the sidebar, below the header button
 m.style.top=Math.max(8,Math.min(top,innerHeight-h-8))+'px';m.style.left=Math.max(8,Math.min(r.right-w,innerWidth-w-8))+'px';
 anchor.setAttribute('aria-expanded','true');m.querySelector('button')?.focus();
}
$('#account-menu').addEventListener('toggle',e=>{if(e.newState==='closed')document.querySelectorAll('[aria-haspopup=menu]').forEach(b=>b.setAttribute('aria-expanded','false'));});
document.addEventListener('click',async e=>{
 const opener=e.target.closest('#account-button, #identity-button');if(opener){openMenu(opener);return;}
 const item=e.target.closest('[data-menu]');if(!item)return;
 try{$('#account-menu').hidePopover();}catch{}
 if(item.dataset.menu==='profile')openProfile();
 if(item.dataset.menu==='history')go('analyze');
 if(item.dataset.menu==='logout'&&await confirmBox({title:'تسجيل الخروج؟',message:'ستحتاج إلى بريدك وكلمة المرور للدخول مرة أخرى.',confirm:'تسجيل الخروج',danger:true})){
  const was=token;signedOut('');if(was)fetch('/api/auth/logout',{method:'POST',headers:{Authorization:'Bearer '+was}}).catch(()=>{});history.replaceState(null,'',location.pathname);
 }
});
// An alert in the manner of Apple's: title, short message, Cancel on the leading side (and the default),
// the action on the trailing side, red when it is destructive. Resolves to false, true, or {value} with a note.
function confirmBox({title,message='',confirm='تأكيد',danger=false,input=null}){
 return new Promise(resolve=>{
  const d=$('#confirm');
  d.innerHTML=`<div class="alert-body"><h3 id="confirm-title">${esc(title)}</h3>${message?`<p>${esc(message)}</p>`:''}${input?`<textarea id="confirm-input" maxlength="1000" placeholder="${esc(input)}"></textarea>`:''}</div><div class="alert-actions"><button type="button" data-alert="cancel">إلغاء</button><button type="button" data-alert="ok" class="${danger?'destructive':'confirm'}">${esc(confirm)}</button></div>`;
  const finish=v=>{closeDialog(d);resolve(v);};
  d.querySelector('[data-alert=cancel]').onclick=()=>finish(false);
  d.querySelector('[data-alert=ok]').onclick=()=>finish(input?{value:$('#confirm-input').value.trim()}:true);
  d.oncancel=e=>{e.preventDefault();finish(false);};
  d.showModal();(input?$('#confirm-input'):d.querySelector('[data-alert=cancel]')).focus();
 });
}
async function openProfile(){
 const d=$('#profile');d.innerHTML=loaderHtml('جارٍ التحميل');d.showModal();
 try{
  const p=await request('/account'),act=p.activity||{};
  const since=p.created_at?new Date(p.created_at).toLocaleDateString('ar-u-nu-latn',{year:'numeric',month:'long',day:'numeric'}):'';
  d.innerHTML=`<header class="profile-head"><span class="avatar-i xl" aria-hidden="true">${esc(initial(p.name))}</span><div><h3 id="profile-title">${esc(p.name)}</h3><p>${esc(p.email||(p.role==='admin'?'حساب تشغيل':''))}</p>${since?`<small>عضو منذ ${esc(since)}</small>`:''}</div><button type="button" class="icon-close" data-action="close-profile" aria-label="إغلاق"><svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="2" d="M18 6 6 18M6 6l12 12"/></svg></button></header>
  <div class="profile-body">
   <section class="stats" aria-label="نشاطك"><div><strong>${num(act.analyses)}</strong><span>تحليل</span></div><div><strong>${num(act.reviews)}</strong><span>مراجعة</span></div><div><strong>${num(act.approved)}</strong><span>اعتماد</span></div></section>
   ${p.editable?`<form id="profile-name-form" class="settings-group"><h4>الاسم</h4><input id="profile-name" value="${esc(p.name)}" maxlength="60" autocomplete="name" required><div class="settings-actions"><button class="primary">حفظ الاسم</button></div></form>
   <form id="profile-email-form" class="settings-group"><h4>البريد الإلكتروني</h4><input id="profile-email" type="email" dir="ltr" value="${esc(p.email)}" autocomplete="email" required><input id="profile-email-password" type="password" placeholder="كلمة المرور الحالية للتأكيد" autocomplete="current-password" required><div class="settings-actions"><button class="primary">تغيير البريد</button></div></form>
   <form id="profile-password-form" class="settings-group"><h4>كلمة المرور</h4><input id="profile-current" type="password" placeholder="كلمة المرور الحالية" autocomplete="current-password" required><input id="profile-new" type="password" placeholder="كلمة المرور الجديدة" autocomplete="new-password" required><ul id="profile-rules" class="pw-rules"><li data-rule="length">8 أحرف على الأقل</li><li data-rule="letter">حرف واحد على الأقل</li><li data-rule="digit">رقم واحد على الأقل</li></ul><small class="muted">تغيير كلمة المرور يُخرجك من الأجهزة الأخرى.</small><div class="settings-actions"><button class="primary">تغيير كلمة المرور</button></div></form>`
   :`<p class="muted settings-note">هذا حساب تشغيل لمسؤول المشروع، ولا يُعدَّل من هنا.</p>`}
   <div class="settings-group danger-zone"><button type="button" data-menu="logout" class="destructive-link">تسجيل الخروج</button></div>
  </div>`;
 }catch(err){closeDialog(d);notify(err.message,'error');}
}
document.addEventListener('input',e=>{if(e.target.id==='profile-new'){const c=passwordChecks(e.target.value);document.querySelectorAll('#profile-rules li').forEach(li=>li.classList.toggle('ok',c[li.dataset.rule]));}});

// ---------- Sign up / sign in ----------
let authMode='signup';
function openAuth(mode){
 authMode=mode;const signup=mode==='signup';
 $('#auth-title').textContent=signup?'إنشاء حساب':'تسجيل الدخول';
 $('#auth-sub').textContent=signup?'اسمك وبريدك وكلمة مرور، ولا شيء غير ذلك.':'أهلًا بعودتك.';
 $('#name-field').hidden=!signup;$('#auth-name').required=signup;$('#pw-rules').hidden=!signup;
 document.querySelectorAll('#auth .field-error').forEach(n=>{n.hidden=true;n.previousElementSibling?.setAttribute('aria-invalid','false');});
 $('#auth-password').autocomplete=signup?'new-password':'current-password';
 $('#auth-submit').textContent=signup?'إنشاء الحساب':'دخول';
 $('#switch-text').textContent=signup?'لديك حساب؟':'ليس لديك حساب؟';$('#auth-switch').textContent=signup?'سجّل الدخول':'أنشئ حسابًا';
 $('#auth-error').hidden=true;
 if(!$('#auth').open)$('#auth').showModal();
 (signup?$('#auth-name'):$('#auth-email')).focus();
}
document.addEventListener('click',e=>{const b=e.target.closest('[data-auth]');if(b)openAuth(b.dataset.auth);});
$('#auth-switch').addEventListener('click',()=>openAuth(authMode==='signup'?'login':'signup'));
// Same rules as the server (src/auth.py): a real-looking email and a medium-strength password.
const EMAIL=/^(?!\.)(?!.*\.\.)[A-Za-z0-9._%+-]{1,64}(?<!\.)@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,24}$/;
const TYPOS={'gmial.com':'gmail.com','gmai.com':'gmail.com','gmail.co':'gmail.com','gmail.con':'gmail.com','gmail.cm':'gmail.com','gamil.com':'gmail.com','gmal.com':'gmail.com','hotmial.com':'hotmail.com','hotmail.con':'hotmail.com','hotmai.com':'hotmail.com','outlok.com':'outlook.com','outlook.con':'outlook.com','yaho.com':'yahoo.com','yahoo.con':'yahoo.com','icloud.con':'icloud.com','iclod.com':'icloud.com'};
const nameProblem=v=>v.replace(/\s+/g,' ').trim().length<2?'اكتب اسمك (حرفان على الأقل).':'';
function emailProblem(v){v=v.trim().toLowerCase();if(!EMAIL.test(v))return 'البريد الإلكتروني غير صحيح. مثال صحيح: name@example.com';const [user,domain]=v.split('@');return TYPOS[domain]?`هل تقصد ${user}@${TYPOS[domain]}؟ تحقق من البريد.`:'';}
const passwordChecks=v=>({length:v.length>=8,letter:/\p{L}/u.test(v),digit:/\d/.test(v)});
function passwordProblem(v,email){const c=passwordChecks(v);if(!c.length)return 'كلمة المرور من 8 أحرف على الأقل.';if(!c.letter||!c.digit)return 'كلمة المرور تحتاج حرفًا ورقمًا على الأقل.';if(v!==v.trim())return 'لا تبدأ كلمة المرور بمسافة ولا تنتهِ بها.';const user=(email||'').toLowerCase().split('@')[0];if(user.length>=5&&v.toLowerCase().includes(user))return 'اختر كلمة مرور لا تحتوي على بريدك.';return '';}
function fieldNote(input,message){let note=input.nextElementSibling;if(!note||!note.classList.contains('field-error')){note=document.createElement('small');note.className='field-error';input.after(note);}note.textContent=message;note.hidden=!message;input.setAttribute('aria-invalid',message?'true':'false');}
$('#auth-email').addEventListener('blur',e=>{if(e.target.value.trim())fieldNote(e.target,emailProblem(e.target.value));});
$('#auth-email').addEventListener('input',e=>{if(e.target.getAttribute('aria-invalid')==='true')fieldNote(e.target,emailProblem(e.target.value));});
$('#auth-name').addEventListener('blur',e=>{if(e.target.value)fieldNote(e.target,nameProblem(e.target.value));});
$('#auth-password').addEventListener('input',e=>{const c=passwordChecks(e.target.value);document.querySelectorAll('#pw-rules li').forEach(li=>li.classList.toggle('ok',c[li.dataset.rule]));});
$('#auth-form').addEventListener('submit',async e=>{
 e.preventDefault();const error=$('#auth-error'),submit=$('#auth-submit');error.hidden=true;
 const body={email:$('#auth-email').value.trim(),password:$('#auth-password').value};
 if(authMode==='signup')body.name=$('#auth-name').value.trim();
 const problem=authMode==='signup'?(nameProblem(body.name)||emailProblem(body.email)||passwordProblem(body.password,body.email)):(emailProblem(body.email)||(body.password?'':'اكتب كلمة المرور.'));
 if(problem){error.textContent=problem;error.hidden=false;return;}
 submit.disabled=true;submit.classList.add('busy');
 try{
  const r=await request('/auth/'+authMode,{method:'POST',body});
  token=r.token;remember.set(token);$('#auth-password').value='';closeDialog($('#auth'));
  if(!titles[location.hash.slice(1)])view='overview';
  await init();notify(authMode==='signup'?`أهلًا ${r.name}، أُنشئ حسابك.`:`أهلًا ${r.name}.`);
 }catch(err){error.textContent=err.message;error.hidden=false;}
 finally{submit.disabled=false;submit.classList.remove('busy');}
});
// Landing header: clear over the photograph, solid once the page scrolls.
const landBar=$('.land-bar'),solidBar=()=>landBar.classList.toggle('solid',window.scrollY>12);
window.addEventListener('scroll',solidBar,{passive:true});solidBar();
// The landing wordmark returns to the top.
$('.land-brand').addEventListener('click',e=>{e.preventDefault();window.scrollTo({top:0});});

// Each tab has its own address (#rules, #review…) so refresh, Back/Forward and shared links keep the place.
function go(next){if(!titles[next])next='overview';offset=0;query='';status=null;if(location.hash.slice(1)!==next){location.hash=next;return;}view=next;render().catch(e=>notify(e.message));}
$('#nav').addEventListener('click',e=>{const b=e.target.closest('[data-view]');if(b)go(b.dataset.view);});
window.addEventListener('hashchange',()=>{const next=location.hash.slice(1);if(titles[next]&&ready){view=next;offset=0;query='';status=null;render().catch(e=>notify(e.message));}});
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
 if(!ready)return;
 renderSeq++;
 const seq=renderSeq;let done=false;$('#content').setAttribute('aria-busy','true');
 // Dim the old page only if the new one takes noticeably long (never after it has already appeared).
 setTimeout(()=>{if(!done&&!stale(seq))$('#content').classList.add('loading');},120);
 $('#breadcrumb').textContent=titles[view];
 document.querySelectorAll('[data-view]').forEach(b=>{const on=b.dataset.view===view;b.classList.toggle('active',on);if(on){b.setAttribute('aria-current','page');centerTab(b);}else b.removeAttribute('aria-current');});
 try{
  const before=$('#content').dataset.view;
  if(view==='overview')await overview();
  else if(view==='analyze')await analyzeView();
  else if(view==='sources')await sourcesView();
  else if(view==='evaluation')await evaluationView();
  else if(view==='export')await exportView();
  else await recordsView();
  if(stale(seq))return;
  if(view!=='objections'&&view!=='external'&&view!=='rules'&&view!=='families'&&view!=='review')$('#content').dataset.view=view;
  if(before!==view)enterPage();
 }finally{done=true;if(!stale(seq)){$('#content').classList.remove('loading');$('#content').removeAttribute('aria-busy');}}
}
// One quiet entrance for the whole page when the tab changes (not on every search or save).
function enterPage(){const c=$('#content');c.classList.remove('page-in');void c.offsetWidth;c.classList.add('page-in');window.scrollTo({top:0});}
const page=r=>r.source?.page_number?'صفحة '+r.source.page_number:'';
const where=r=>[r.source?.source_name,page(r)].filter(Boolean).join('، ');
async function overview(){
 const seq=renderSeq;
 const [s,records]=await Promise.all([api('/summary'),api('/records?kind=objection&status=needs_review&limit=5')]);
 if(stale(seq))return;
 const figures=[['المصادر',s.sources,'كتاب وليد'],['الشبهات',s.objections,'استُخرجت من نص الكتاب'],['القواعد المنهجية',s.rules,'تُراجع قبل استخدامها'],['بانتظار المراجعة',s.pending,`${num(s.approved)} سجل معتمد`]];
 // The page leads with analysing an objection; the queue and the method follow.
 $('#content').innerHTML=title('نظرة عامة','ما ينتظر المراجعة في المشروع الآن.')+
 `<section class="analyze-cta"><div><h3>حلّل شبهة</h3><p>اكتب شبهة واحصل على تشخيص مقترح من قواعد الكتاب. كل تحليل يُحفظ في سجلك.</p></div><button class="primary big" data-go="analyze">ابدأ تحليلًا</button></section>
 <div class="metrics">${figures.map(([label,n,note])=>`<div class="metric"><div class="label">${label}</div><strong>${num(n)}</strong><small>${note}</small></div>`).join('')}</div>
 <div class="two-col">
  <section class="card"><div class="card-head"><h3>بانتظار المراجعة</h3><button class="quiet" data-go="review">عرض الكل</button></div>${records.items.map(r=>`<div class="row"><div class="text"><h4>${esc(ar(r.title_ar))}</h4><p>${esc(where(r))}</p></div><button data-open="${esc(r.id)}">مراجعة</button></div>`).join('')||'<div class="empty">لا توجد حالات بانتظار المراجعة.</div>'}</section>
  <section class="card method"><h3>كيف تُحلَّل الشبهة؟</h3><p>أصل المنهج أن الشريعة لا تفرّق بين المتماثلات ولا تجمع بين المختلفات: فإما جمعٌ بين مختلفين يُرد ببيان الفرق المؤثر، وإما تفريقٌ بين متماثلين يُرد ببيان وجه التماثل.</p><ol><li>تحديد ما يدّعيه المعترض</li><li>تحديد الطرفين المقارَن بينهما</li><li>جمعٌ بين مختلفين أم تفريقٌ بين متماثلين؟</li><li>ربطه بقاعدة من الكتاب</li><li>صياغة الرد ثم مراجعته من مختص</li></ol></section>
 </div>`;
}
// ---------- Analyse an objection, with the reviewer's own history ----------
const when=iso=>iso?new Date(iso).toLocaleString('ar-u-nu-latn',{day:'numeric',month:'long',year:'numeric',hour:'numeric',minute:'2-digit'}):'';
const verdictPill=d=>d.abstention_reason?'<span class="pill pending">لم يُصنَّف</span>':`<span class="pill">${esc(patternName(d.primary_pattern))}</span>`;
function historyItem(d){
 const flags=(d.mode==='draft'?'<span class="pill draft">مسودة</span>':'')+(d.feedback?.verdict==='wrong'?'<span class="pill rejected">أُبلغ عن خطأ</span>':d.feedback?.verdict==='correct'?'<span class="pill">صحيح</span>':'');
 return `<article class="h-item" id="h-${esc(d.id)}"><button type="button" class="h-main" data-diag="${esc(d.id)}" aria-expanded="false"><time>${esc(when(d.created_at))}</time><p>${esc(ar(d.input_ar))}</p><span class="h-tags">${verdictPill(d)}${flags}</span></button><button type="button" class="icon-btn" data-del-diag="${esc(d.id)}" aria-label="حذف من السجل"><svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></g></svg></button><div class="h-detail" hidden></div></article>`;
}
const emptyHistory=`<div class="empty-art"><img src="/static/img/empty-history.webp" alt="" width="280" height="210" loading="lazy"><p>لم تحلّل أي شبهة بعد. اكتب أول شبهة في الأعلى، وستجدها هنا مع نتيجتها.</p></div>`;
let historyShown=0;
async function refreshHistory(append=false){
 const box=$('#history-list');if(!box)return;
 const data=await api(`/diagnoses?limit=20&offset=${append?historyShown:0}`);
 historyShown=(append?historyShown:0)+data.items.length;
 if(append)box.insertAdjacentHTML('beforeend',data.items.map(historyItem).join(''));else box.innerHTML=data.items.map(historyItem).join('')||emptyHistory;
 $('#history-count').textContent=data.total?countLabel(data.total).replace('سجل','تحليل').replace('سجلات','تحليلات').replace('سجلان','تحليلان'):'';
 $('#history-more').hidden=historyShown>=data.total;
}
async function analyzeView(){
 const seq=renderSeq;
 $('#content').innerHTML=title('حلّل شبهة','اكتب الشبهة كما سمعتها أو قرأتها. يقترح النظام تشخيصًا مستندًا إلى قواعد الكتاب، ويحفظه في سجلك.')+
 `<section class="analyze">
  <form id="diagnose-form">
   <label for="diagnose-text" class="sr-only">نص الشبهة</label>
   <textarea id="diagnose-text" required maxlength="12000" placeholder="مثال: لماذا تقولون إن الحكم واحد مع أن الحالتين مختلفتان؟"></textarea>
   <div class="analyze-foot">
    <label class="check"><input id="diagnose-drafts" type="checkbox">استخدم أيضًا القواعد التي لم تُراجع بعد (تُعلَّم النتيجة «مسودة»)</label>
    <div class="form-actions">${caps.semantic&&!caps.read_only?'<button type="button" class="quiet" data-action="refresh-index">تحديث البحث بعد التعديلات</button>':''}<button class="primary big" id="diagnose-submit">حلّل الشبهة</button></div>
   </div>
  </form>
  <p class="ai-note">النتيجة اقتراح آلي يساعد في البحث، وليست فتوى ولا حكمًا. لا تُعتمد قبل أن يراجعها مختص.</p>
  <div id="diagnosis-result" aria-live="polite"></div>
 </section>
 <section class="my-history"><div class="card-head"><h3>سجل تحليلاتك</h3><span class="muted" id="history-count"></span></div><div id="history-list">${loaderHtml('جارٍ تحميل السجل')}</div><button type="button" id="history-more" class="more-btn" hidden>عرض المزيد</button></section>`;
 try{await refreshHistory();}catch(err){if(!stale(seq))$('#history-list').innerHTML=`<p class="muted">${esc(err.message)}</p>`;}
}
async function recordsView(){
 const seq=renderSeq;
 const chosen=status===null?(view==='review'?'needs_review':''):status;
 const data=await api(recordsPath(view,offset,query,chosen));
 if(!data.items.length&&offset>0&&offset>=data.total){offset=Math.max(0,Math.ceil(data.total/30)*30-30);return render();}
 let extra='';
 if(view==='external')extra=!caps.heavy_jobs?'<p class="lead-note">يضيفها مسؤول المشروع من مصادر موثوقة، وتظهر هنا لتراجعها.</p>':`<div class="banner">يبدأ جمع الشبهات من مصادر أخرى بعد إنهاء مراجعة الكتاب كاملًا، وكل نتيجة تدخل قائمة المراجعة.</div><details class="card spaced"><summary>البحث في المصادر المسموح بها</summary><form id="research-form"><label for="research-topic">الموضوع</label><input id="research-topic" required><label for="research-limit">أقصى عدد من النتائج</label><input id="research-limit" type="number" min="1" max="50" value="5"><button class="primary spaced">ابحث</button></form><form id="gate-form"><label class="check"><input id="coverage-check" type="checkbox" required>أشهد بأن مراجعة جميع شبهات الكتاب وقواعده اكتملت.</label><label for="coverage-notes">ملاحظات المراجعة</label><textarea id="coverage-notes" required></textarea><button class="spaced">توثيق اكتمال مراجعة الكتاب</button></form></details>`;
 const actions=!caps.heavy_jobs?'':view==='families'?'<button data-action="families">اقترح مجموعات متشابهة</button>':view==='objections'?'<button data-action="duplicates">ابحث عن المكرر</button>':'';
 if(stale(seq))return;
 // Searching and paging refresh only the table, so the search box keeps focus while typing.
 if($('#content').dataset.view===view&&$('#records-table')){
  $('#records-count').textContent=countLabel(data.total);
  const box=$('#records-table');box.innerHTML=tableHtml(data);box.classList.remove('refresh');void box.offsetWidth;box.classList.add('refresh');
  return;
 }
 $('#content').dataset.view=view;
 $('#content').innerHTML=title(titles[view],'',actions).replace('<p></p>',`<p id="records-count">${countLabel(data.total)}</p>`)+extra+`<div class="toolbar spaced"><input id="search" type="search" aria-label="بحث" placeholder="ابحث في العنوان أو النص" value="${esc(query)}" autocomplete="off"><select id="status-filter" aria-label="حالة المراجعة"><option value="" ${chosen===''?'selected':''}>جميع الحالات</option>${Object.entries(statuses).map(([k,v])=>`<option value="${k}" ${chosen===k?'selected':''}>${v}</option>`).join('')}</select></div><section class="card" id="records-table">${tableHtml(data)}</section>`;
}
const countLabel=n=>n===0?'لا سجلات':n===1?'سجل واحد':n===2?'سجلان':n<=10?`${num(n)} سجلات`:`${num(n)} سجل`;
function tableHtml(data){
 const last=Math.min(offset+30,data.total);
 return `<div class="table-wrap"><table><thead><tr><th>العنوان</th><th>التشخيص</th><th>المصدر</th><th>الحالة</th><th><span class="sr-only">إجراء</span></th></tr></thead><tbody>${data.items.map(r=>`<tr><td>${esc(ar(r.title_ar))}<small dir="ltr">${esc(r.id)}</small></td><td>${esc(patternName(r.primary_pattern))}<small>${esc(r.sub_patterns.map(subName).join('، '))}</small></td><td>${esc(r.source?.source_name||'مجموعة مقترحة')}<small>${esc(page(r))}</small></td><td>${badge(r.review_status)}</td><td><button data-open="${esc(r.id)}">فتح</button></td></tr>`).join('')}</tbody></table>${data.items.length?'':`<div class="empty">${query?'لا شيء يطابق «'+esc(query)+'».':'القائمة فارغة.'}</div>`}</div>${data.total>30?`<div class="pagination"><span>${num(offset+1)} إلى ${num(last)} من ${num(data.total)}</span><div><button data-page="prev" ${offset===0?'disabled':''}>السابق</button> <button data-page="next" ${offset+30>=data.total?'disabled':''}>التالي</button></div></div>`:''}`;
}
// Results follow the search box as you type (after a short pause) and the status list at once.
let searchTimer;
document.addEventListener('input',e=>{if(e.target.id!=='search')return;clearTimeout(searchTimer);searchTimer=setTimeout(()=>{query=e.target.value.trim();offset=0;render().catch(err=>notify(err.message,'error'));},280);});
document.addEventListener('change',e=>{if(e.target.id!=='status-filter')return;status=e.target.value;offset=0;render().catch(err=>notify(err.message,'error'));});
async function sourcesView(){
 const seq=renderSeq;
 const sources=await api('/sources');
 if(stale(seq))return;
 $('#content').innerHTML=title('المصادر','الكتب التي استُخرجت منها الشبهات والقواعد.')+`<div class="list-stack">${sources.map(s=>`<article class="card source-card"><img class="book-cover" src="/static/img/book-cover.webp" alt="" width="72" height="96"><div class="text"><h3>${esc(s.source_name)}</h3><p>${esc([s.actual_title,s.author].filter(Boolean).join('، '))}</p><p>${s.page_count?num(s.page_count)+' صفحة':''}</p></div><div class="source-actions"><button class="primary" data-book="${esc(s.id)}" data-bookpage="1" data-booktitle="${esc(s.source_name)}">اقرأ الكتاب</button><button data-chunks="${esc(s.id)}">النص مقسّمًا</button></div></article>`).join('')}</div>${!caps.heavy_jobs?'<p class="lead-note spaced">لإضافة كتاب جديد تواصل مع مسؤول المشروع.</p>':`<details class="card spaced"><summary>إضافة كتاب PDF</summary><form id="ingest-form"><label for="pdf-title">اسم الكتاب</label><input id="pdf-title" value="كتاب وليد" required><label for="pdf-author">المؤلف كما يظهر في الكتاب</label><input id="pdf-author"><label for="pdf-profile">طريقة ترتيب النص</label><select id="pdf-profile"><option value="standard">عادية</option><option value="rtl_visual">حروف معكوسة الترتيب (مثل الكتاب الحالي)</option></select><label for="pdf-file">ملف PDF</label><input id="pdf-file" type="file" accept="application/pdf" required><button class="primary spaced">استخراج إلى قائمة المراجعة</button></form></details>`}`;
}
async function evaluationView(){
 const seq=renderSeq;
 const [manifests,runs]=await Promise.all([api('/documents/dataset_manifests'),api('/documents/evaluation_runs')]);
 if(stale(seq))return;
 $('#content').innerHTML=title('التقييم','نختبر دقة التحليل على حالات معتمدة لم يرها النظام من قبل.')+`<div class="two-col"><section class="card"><h3>إنشاء مجموعة اختبار</h3><form id="benchmark-form"><label for="test-ids">أرقام حالات الاختبار المعتمدة (سطر لكل حالة)</label><textarea id="test-ids" required dir="ltr"></textarea><label for="validation-ids">أرقام حالات التحقق (اختياري)</label><textarea id="validation-ids" dir="ltr"></textarea><button class="primary spaced">حفظ المجموعة</button></form></section><section class="card"><h3>المجموعات المحفوظة</h3>${manifests.map(m=>`<div class="row"><div><small dir="ltr">${esc(m.id)}</small><p>تدريب ${num(m.payload.training_ids.length)}، تحقق ${num(m.payload.validation_ids.length)}، اختبار ${num(m.payload.test_ids.length)}</p></div></div>`).join('')||'<div class="empty">لا توجد مجموعات بعد.</div>'}</section></div><section class="card spaced"><h3>نتائج التقييم</h3>${runs.map(r=>`<details><summary>${esc(r.id)}</summary><pre class="json">${esc(JSON.stringify(r.payload.metrics,null,2))}</pre></details>`).join('')||'<div class="empty">لم يُجرَ تقييم بعد.</div>'}</section>`;
}
async function exportView(){
 const seq=renderSeq;
 const [manifests,exports]=await Promise.all([api('/documents/dataset_manifests'),api('/documents/training_exports')]);
 if(stale(seq))return;
 $('#content').innerHTML=title('تصدير البيانات','تُصدَّر الحالات المعتمدة فقط، وتُستبعد حالات الاختبار.')+`<div class="two-col"><section class="card"><h3>ملف التدريب</h3><form id="export-form"><label for="manifest">مجموعة البيانات</label><select id="manifest" required><option value="">اختر مجموعة</option>${manifests.map(m=>`<option value="${esc(m.id)}">${esc(m.id)} (${num(m.payload.training_ids.length)} حالة تدريب)</option>`).join('')}</select><button class="primary spaced">تنزيل ملف التدريب</button></form><button data-action="json-export" class="spaced">تنزيل كل السجلات المعتمدة</button></section><section class="card"><h3>عمليات التصدير السابقة</h3>${exports.map(x=>`<div class="row"><div><small>${esc(new Date(x.payload.at).toLocaleString('ar-u-nu-latn'))}</small><p>${num(x.payload.records_count??0)} حالة</p></div></div>`).join('')||'<div class="empty">لا توجد عمليات تصدير.</div>'}</section></div>`;
}

// ---------- Review window ----------
// PDF extraction keeps the printed line breaks; join them for reading and keep real paragraph breaks.
const reflow=text=>String(text||'').replace(/([^\n])[ \t]*\n[ \t]*(?=[^\n])/g,'$1 ').trim();
function field(id,label,value,{rows=false,hint='',line=false}={}){
 return `<div class="field"><label for="edit-${id}">${label}</label>${hint?`<small class="hint">${hint}</small>`:''}${rows||line?`<textarea id="edit-${id}" rows="1"${line?' class="one-line"':''}>${esc(value)}</textarea>`:`<input id="edit-${id}" value="${esc(value)}">`}</div>`;
}
// Text boxes grow with their content, so the review form never shows scrollbars inside scrollbars.
function grow(el){el.style.height='auto';el.style.height=el.scrollHeight+2+'px';}
let editorStart=new Map(); // field values as first shown, so saving sends only what the reviewer changed
const changed=el=>el&&el.value!==editorStart.get(el.id);
document.addEventListener('input',e=>{if(e.target.matches('#editor textarea'))grow(e.target);});
async function openRecord(id){
 const [r,rules]=await Promise.all([api('/records/'+id),api('/records?kind=rule&limit=200')]);currentRecord=r;
 const patterns=[...Object.keys(taxonomy),'mixed_pattern','multiple_claims','unknown','insufficient_evidence','requires_human_review'];
 const kindName=r.kind==='rule'?'القاعدة':r.kind==='family'?'مجموعة الشبهات':'الشبهة';
 const diagnosisPicker=`<div class="fields-two"><div class="field"><label for="edit-pattern">التشخيص</label><select id="edit-pattern">${patterns.map(p=>`<option value="${esc(p)}" ${p===r.primary_pattern?'selected':''}>${esc(patternName(p))}</option>`).join('')}</select></div><div class="field"><label for="edit-subpatterns">تفصيل التشخيص</label><select id="edit-subpatterns" multiple size="4">${Object.values(taxonomy).flat().map(p=>`<option value="${esc(p)}" ${r.sub_patterns.includes(p)?'selected':''}>${esc(subName(p))}</option>`).join('')}</select></div></div>`;
 const facts=[['المؤلف',r.source?.author],['الصفحة',r.source?.page_number],['الموضع',(r.source?.section||'').replace(/\s*:\s*$/,'')]].filter(([,v])=>v);
 const ruleField=r.kind==='rule'
  ? field('methodology_rule_ar','نص القاعدة كما في الكتاب',ar(reflow(r.methodology_rule_ar)),{rows:true,hint:'انسخه حرفيًا من نص الكتاب المجاور.'})
  : `<div class="field"><label for="edit-ruleids">القواعد المرتبطة</label><small class="hint">الاعتماد يتطلب أن تكون القواعد المرتبطة معتمدة.</small><select id="edit-ruleids" multiple size="5">${rules.items.filter(x=>x.review_status!=='rejected'||r.methodology_rule_ids.includes(x.id)).map(x=>`<option value="${esc(x.id)}" ${r.methodology_rule_ids.includes(x.id)?'selected':''}>${esc(x.title_ar)}${x.review_status==='approved'?'':' ('+esc(statuses[x.review_status]||x.review_status)+')'}</option>`).join('')}</select></div>`;
 $('#editor-content').innerHTML=`<header class="modal-head"><div class="modal-title"><h3 id="editor-title">مراجعة ${kindName}</h3>${badge(r.review_status)}<small class="muted" dir="ltr">${esc(r.id)}</small><small class="muted">الإصدار ${num(r.version)}</small></div><button data-action="close">إغلاق</button></header>
 <div class="modal-grid">
  <section class="evidence-pane" aria-label="نص الكتاب">
   <div class="evidence-head"><h4>${esc(r.source?.source_name||'مجموعة مقترحة')}</h4>${r.source?.source_type==='book'?`<button data-book="${esc(r.source.source_id)}" data-bookpage="${r.source.page_number||1}" data-booktitle="${esc(r.source.source_name)}">افتح الصفحة في الكتاب</button>`:''}</div>
   ${facts.length?`<dl class="facts">${facts.map(([k,v])=>`<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>`:''}
   <div class="excerpt">${esc(ar(reflow(r.source?.source_excerpt||r.common_variants_ar.join('\n\n'))))}</div>
   <details class="history"><summary data-history="${esc(r.id)}">سجل التعديلات</summary><ol id="history"></ol></details>
  </section>
  <form id="review-form" class="review-pane">
   ${r.kind==='rule'
    ? `<fieldset><legend>القاعدة</legend>${field('title_ar','العنوان',ar(r.title_ar),{line:true})}${ruleField}</fieldset>
       <fieldset><legend>التصنيف</legend>${diagnosisPicker}${field('treatment_ar','كيف تُطبَّق القاعدة',r.treatment_ar,{rows:true})}</fieldset>`
    : `<fieldset><legend>${r.kind==='family'?'المجموعة':'الشبهة'}</legend>${field('title_ar','العنوان',ar(r.title_ar),{line:true})}${r.kind==='objection'?field('objection_text_ar','نص الشبهة',ar(reflow(r.objection_text_ar)),{rows:true,hint:'العبارة كما وردت في نص الكتاب.'}):''}${r.kind==='family'?field('core_claim_ar','الدعوى المشتركة',r.core_claim_ar,{rows:true})+field('core_confusion_ar','موضع الالتباس المشترك',r.core_confusion_ar,{rows:true}):''}</fieldset>
       <fieldset><legend>التحليل</legend>${field('central_claim_ar','ما يدّعيه المعترض',r.central_claim_ar,{rows:true,hint:'أعد صياغة الدعوى بإيجاز.'})}${field('subclaims_ar','تفاصيل الدعوى',r.subclaims_ar.join('\n'),{rows:true,hint:'سطر لكل نقطة.'})}${field('compared_entities_ar','طرفا المقارنة',r.compared_entities_ar.map(x=>x.entity_a+' | '+x.entity_b).join('\n'),{rows:true,hint:'كل سطر: الطرف الأول | الطرف الثاني'})}${diagnosisPicker}${field('diagnostic_reason_ar','سبب التشخيص',r.diagnostic_reason_ar,{rows:true})}</fieldset>
       <fieldset><legend>الرد</legend>${field('revealing_question_ar','سؤال يكشف الإشكال',r.revealing_question_ar,{rows:true})}${ruleField}${field('treatment_ar','طريقة المعالجة',r.treatment_ar,{rows:true})}${field('response_path_ar','خطوات الرد',r.response_path_ar.join('\n'),{rows:true,hint:'سطر لكل خطوة.'})}</fieldset>`}
   <details class="more"><summary>التكرار والتشابه</summary>${field('duplicate_group_id','رقم مجموعة التكرار',r.duplicate_group_id||'')}${field('family_id','رقم مجموعة التشابه',r.family_id||'')}<div class="field"><label for="edit-similarity">نوع التشابه</label><select id="edit-similarity">${Object.entries(similarityNames).map(([x,name])=>`<option value="${x}" ${x===r.similarity_type?'selected':''}>${name}</option>`).join('')}</select></div></details>
   ${field('notes','ملاحظات المراجع',r.reviewer_notes,{rows:true})}
  </form>
 </div>
 <footer class="modal-foot"><div class="attest"><label class="check"><input id="verify-source" type="checkbox" form="review-form">المقتطف مطابق للكتاب ومنسوب لقائله</label><label class="check"><input id="verify-page" type="checkbox" form="review-form">رقم الصفحة صحيح</label><label class="check"><input id="verify-diagnosis" type="checkbox" form="review-form">راجعت الدعوى والتشخيص</label></div><div class="actions"><button class="danger" form="review-form" name="action" value="reject">رفض</button><button form="review-form" name="action" value="edit">حفظ دون اعتماد</button><button class="primary" form="review-form" name="action" value="approve">اعتماد</button></div></footer>`;
 editorStart=new Map([...document.querySelectorAll('#review-form [id^="edit-"]')].map(el=>[el.id,el.multiple?[...el.selectedOptions].map(o=>o.value).join():el.value]));
 $('#editor').showModal();
 $('#editor .review-pane').scrollTop=0;$('#editor .evidence-pane').scrollTop=0;
 document.querySelectorAll('#editor textarea').forEach(grow);
}

// ---------- Book viewer: the original pages inside the site ----------
const book={sid:null,page:1,total:1,urls:new Map(),title:''};
const spread=()=>window.matchMedia('(min-width: 900px)').matches?2:1;
async function pageUrls(start){
 const want=[];for(let n=start;n<start+spread()&&n<=book.total;n++){const hit=book.urls.get(n);if(!hit||Date.now()-hit.at>600000)want.push(n);}
 if(want.length){const data=await request(`/sources/${book.sid}/pages?start=${want[0]}&count=8`);book.total=data.page_count;
  for(const p of data.pages){let url=p.url;if(url&&url.startsWith('/api/')){url=URL.createObjectURL(await request(url.slice(4),{blob:true}));}book.urls.set(p.number,{url,at:Date.now()});}}
 return [...Array(spread()).keys()].map(i=>start+i).filter(n=>n<=book.total).map(n=>({number:n,url:book.urls.get(n)?.url}));
}
const wait=ms=>new Promise(done=>setTimeout(done,ms));
// Images and animations are given a deadline so a hidden tab or a slow image can never freeze the book.
const preload=url=>Promise.race([new Promise(done=>{const img=new Image();img.onload=img.onerror=done;img.src=url;}),wait(6000)]);
const settle=(anim,ms)=>Promise.race([anim.finished.catch(()=>{}),wait(ms+150)]);
const calm=()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const leafHtml=p=>p.url?`<figure class="leaf"><img src="${esc(p.url)}" alt="صفحة ${p.number}"><figcaption>${num(p.number)}</figcaption></figure>`:`<figure class="leaf missing"><p>صورة الصفحة ${num(p.number)} غير متاحة.</p></figure>`;
let turning=false;
// Turning a page: the open page lifts over the spine, then the new page settles on the other side.
// The book reads right to left, so "next" lifts the left page and "previous" lifts the right one.
async function showPages(target,dir=0){
 target=Math.max(1,Math.min(target,book.total));
 if(turning||(target===book.page&&dir))return;
 turning=true;
 try{
  const stage=$('#book-stage');
  const pages=await pageUrls(target);
  await Promise.all(pages.filter(p=>p.url).map(p=>preload(p.url))); // never flip to a blank page
  const leaves=[...stage.querySelectorAll('.leaf')];
  const motion=dir&&leaves.length&&!calm();
  if(motion){
   const lift=dir>0?leaves[leaves.length-1]:leaves[0];
   lift.style.transformOrigin=dir>0?'right center':'left center';
   lift.classList.add('lifting');
   await settle(lift.animate([{transform:'rotateY(0deg)'},{transform:`rotateY(${dir>0?90:-90}deg)`}],{duration:230,easing:'cubic-bezier(.45,0,.8,.4)',fill:'forwards'}),230);
  }
  book.page=target;
  stage.innerHTML=pages.map(leafHtml).join('');
  stage.classList.remove('turning');
  if(motion){
   const fresh=[...stage.querySelectorAll('.leaf')];
   const land=fresh.length>1?(dir>0?fresh[0]:fresh[fresh.length-1]):fresh[0];
   land.style.transformOrigin=dir>0?'left center':'right center';
   land.classList.add('lifting');
   await settle(land.animate([{transform:`rotateY(${dir>0?-90:90}deg)`},{transform:'rotateY(0deg)'}],{duration:260,easing:'cubic-bezier(.2,.6,.35,1)'}),260);
   land.classList.remove('lifting');
  }
 }finally{turning=false;}
 $('#book-page').value=book.page;$('#book-total').textContent=num(book.total);
 $('[data-turn="prev"]').disabled=book.page<=1;$('[data-turn="next"]').disabled=book.page+spread()>book.total;
 if(book.page+spread()<=book.total)pageUrls(book.page+spread()).then(next=>next.forEach(p=>p.url&&preload(p.url))).catch(()=>{}); // warm the next spread
}
async function openBook(sid,startPage,name){
 book.sid=sid;book.title=name||'الكتاب';book.total=Math.max(startPage,1);
 const d=$('#book');
 d.innerHTML=`<header class="book-bar"><h3 id="book-title">${esc(book.title)}</h3><div class="book-nav"><button data-turn="prev" aria-label="الصفحة السابقة">السابق</button><label class="goto">صفحة <input id="book-page" type="number" min="1" inputmode="numeric"> من <span id="book-total"></span></label><button data-turn="next" aria-label="الصفحة التالية">التالي</button></div><div class="book-tools"><a id="book-download" target="_blank" rel="noopener" hidden>تنزيل PDF</a><button data-action="close-book">إغلاق</button></div></header><div id="book-stage" class="book-stage turning" dir="rtl"></div>`;
 d.showModal();
 const first=await request(`/sources/${sid}/pages?start=1&count=1`).catch(()=>null);if(first)book.total=first.page_count;
 book.page=0;await showPages(startPage);
 api(`/sources/${sid}/pdf-url`).then(link=>{if(link.url){const a=$('#book-download');a.href=link.url;a.hidden=false;}}).catch(()=>{});
}
$('#book').addEventListener('keydown',e=>{if(e.target.id==='book-page')return;if(e.key==='ArrowLeft'){e.preventDefault();showPages(book.page+spread(),1);}if(e.key==='ArrowRight'){e.preventDefault();showPages(book.page-spread(),-1);}});
$('#book').addEventListener('change',e=>{if(e.target.id==='book-page'){const n=Number(e.target.value)||1;showPages(n,Math.sign(n-book.page));}});
let touchX=null;
$('#book').addEventListener('touchstart',e=>{touchX=e.touches[0].clientX;},{passive:true});
$('#book').addEventListener('touchend',e=>{if(touchX===null)return;const dx=e.changedTouches[0].clientX-touchX;touchX=null;if(Math.abs(dx)>60)showPages(book.page+(dx>0?spread():-spread()),dx>0?1:-1);});

const abstentions={no_approved_methodology:'لا توجد قاعدة معتمدة تناسب هذه الشبهة بعد، فلم يصنّفها النظام. يمكنك تفعيل خيار القواعد التي لم تُراجع.',model_not_configured:'خدمة التحليل غير مفعّلة.',model_or_grounding_validation_failed:'لم يستند اقتراح النظام إلى قواعد الكتاب، فاستُبعد.',retrieval_unavailable:'تعذر البحث في الكتاب الآن. حاول بعد قليل.',safety_gate:'أوقف النظام نتيجة خرجت عن حدود التشخيص.'};
function diagnosisHtml(r){
 const a=r.analysis,draft=r.mode==='draft',item=(label,value)=>value&&String(value).trim()?`<dt>${label}</dt><dd>${esc(ar(value))}</dd>`:'';
 const list=(label,values)=>values&&values.length?`<dt>${label}</dt><dd><ol>${values.map(x=>`<li>${esc(x)}</li>`).join('')}</ol></dd>`:'';
 const cites=r.source_evidence.map(c=>`<li><button class="quiet" data-book="${esc(c.source?.source_id||'')}" data-bookpage="${c.source?.page_number||1}" data-booktitle="${esc(c.source?.source_name||'')}">${esc(c.source?.source_name||'')}، صفحة ${c.source?.page_number??''}</button> ${badge(c.review_status||'approved')}</li>`).join('');
 const note=r.abstention_reason?(abstentions[r.abstention_reason]||'لم يصنّف النظام هذه الشبهة.'):'اقتراح مستند إلى قواعد الكتاب، يحتاج مراجعة مختص.';
 const confidence=a.confidence!=null&&!r.abstention_reason?` درجة الثقة ${Math.round(a.confidence*100)}%.`:'';
 return `<div class="verdict">${draft?'<span class="pill draft">مسودة</span>':''}<strong>${esc(patternName(a.primary_pattern))}</strong><span class="pill pending">يحتاج مراجعة مختص</span></div><dl class="diagnosis">${item('ما يدّعيه المعترض',a.central_claim_ar)}${list('تفاصيل الدعوى',a.subclaims_ar)}${list('طرفا المقارنة',a.compared_entities_ar.map(x=>x.entity_a+' مقابل '+x.entity_b))}${list('تفصيل التشخيص',a.sub_patterns.map(subName))}${item('سبب التشخيص',a.diagnostic_reason_ar)}${item('سؤال يكشف الإشكال',a.revealing_question_ar)}${item('القاعدة من الكتاب',a.methodology_rule_ar)}${item('طريقة المعالجة',a.treatment_ar)}${list('خطوات الرد',a.response_path_ar)}${cites?`<dt>المصادر</dt><dd><ul class="cites">${cites}</ul></dd>`:''}</dl><small class="meta">${esc(note)}${confidence}</small>${r.id?`<div class="feedback" data-fb="${esc(r.id)}"><span>هل التحليل صحيح؟</span><button type="button" data-fb-verdict="correct" class="${r.feedback?.verdict==='correct'?'chosen':''}">صحيح</button><button type="button" data-fb-verdict="wrong" class="${r.feedback?.verdict==='wrong'?'chosen':''}">فيه خطأ</button></div>`:''}`;
}
async function download(blob,name){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),30000);}
document.addEventListener('click',async e=>{
 const b=e.target.closest('button, summary[data-history]');if(!b)return;
 if(b.tagName==='BUTTON'&&(b.dataset.open||b.dataset.book||b.dataset.chunks||b.dataset.action==='duplicates'||b.dataset.action==='families'||b.dataset.action==='refresh-index'||b.dataset.action==='json-export'))b.classList.add('busy');
 try{
 if(b.dataset.go)go(b.dataset.go);
 if(b.dataset.open)await openRecord(b.dataset.open);
 if(b.dataset.page){offset=Math.max(0,offset+(b.dataset.page==='next'?30:-30));await render();}
 if(b.dataset.book)await openBook(b.dataset.book,Number(b.dataset.bookpage)||1,b.dataset.booktitle);
 if(b.dataset.turn)await showPages(book.page+(b.dataset.turn==='next'?spread():-spread()),b.dataset.turn==='next'?1:-1);
 if(b.dataset.chunks){const chunks=await api('/sources/'+b.dataset.chunks+'/chunks');$('#editor-content').innerHTML='<header class="modal-head"><div class="modal-title"><h3 id="editor-title">نص الكتاب مقسّمًا</h3></div><button data-action="close">إغلاق</button></header><div class="chunks">'+chunks.map(c=>`<details><summary>صفحة ${num(c.page_number)}: ${esc(c.section)}</summary><pre class="excerpt">${esc(ar(c.text))}</pre></details>`).join('')+'</div>';$('#editor').showModal();}
 if(b.dataset.history&&!b.closest('details').open){const history=await api('/records/'+b.dataset.history+'/history');$('#history').innerHTML=history.map(x=>`<li><b>الإصدار ${num(x.snapshot.version)}</b> ${esc(historyActions[x.action]||x.action)}، ${esc(/^machine:/.test(x.actor)?'النظام':x.actor_name||x.actor)}، ${esc(new Date(x.at).toLocaleString('ar-u-nu-latn'))}</li>`).join('');}
 const action=b.dataset.action;
 if(action==='close')closeDialog($('#editor'));
 if(action==='close-book')closeDialog($('#book'));
 if(action==='close-auth')closeDialog($('#auth'));
 if(action==='close-profile')closeDialog($('#profile'));
 if(b.id==='history-more')await refreshHistory(true);
 if(b.dataset.diag){const item=b.closest('.h-item'),box=item.querySelector('.h-detail'),open=!box.hidden;box.hidden=open;b.setAttribute('aria-expanded',String(!open));if(!open&&!box.dataset.loaded){box.innerHTML=loaderHtml('جارٍ التحميل');box.innerHTML=diagnosisHtml(await api('/diagnoses/'+b.dataset.diag));box.dataset.loaded='1';}}
 if(b.dataset.delDiag&&await confirmBox({title:'حذف هذا التحليل؟',message:'سيُحذف من سجلك نهائيًا، ولا يمكن استرجاعه.',confirm:'حذف',danger:true})){await api('/diagnoses/'+b.dataset.delDiag,{method:'DELETE'});const item=$('#h-'+CSS.escape(b.dataset.delDiag));item?.remove();notify('حُذف التحليل من سجلك.');refreshHistory().catch(()=>{});}
 if(b.dataset.fbVerdict){const holder=b.closest('[data-fb]');let note='';if(b.dataset.fbVerdict==='wrong'){const r=await confirmBox({title:'ما الخطأ في التحليل؟',message:'ملاحظتك تُحفظ مع التحليل ليراجعها المختصون.',confirm:'إرسال',input:'مثال: القاعدة لا تناسب الشبهة، أو التشخيص معكوس'});if(!r)return;note=r.value;}
  await api('/diagnoses/'+holder.dataset.fb+'/feedback',{method:'POST',body:{verdict:b.dataset.fbVerdict,note}});holder.querySelectorAll('button').forEach(x=>x.classList.toggle('chosen',x===b));notify(b.dataset.fbVerdict==='wrong'?'شكرًا، سُجّلت ملاحظتك.':'شكرًا لتأكيدك.');}
 if(action==='duplicates'){b.disabled=true;await api('/duplicates',{method:'POST'});notify('اكتمل البحث عن المكرر، والاقتراحات تنتظر المراجعة.');}
 if(action==='families'){b.disabled=true;const r=await api('/families',{method:'POST'});notify('مجموعات مقترحة جديدة: '+num(r.created.length));await render();}
 if(action==='refresh-index'){b.disabled=true;await api('/embeddings/refresh',{method:'POST',body:{include_drafts:true}});notify('حُدّث البحث.');}
 if(action==='json-export')await download(await api('/export-json',{blob:true}),'manhaj-approved.json');
 }catch(err){notify(err.message,'error');}finally{if(b.tagName==='BUTTON'){b.disabled=false;b.classList.remove('busy');}}
});
document.addEventListener('submit',async e=>{
 if(e.target.id==='auth-form')return;
 e.preventDefault();const button=e.submitter;if(e.target.id==='review-form'&&!button?.value)return;
 // approving needs the three checks: say so right here instead of after a round trip
 if(e.target.id==='review-form'&&button.value==='approve'){
  const needed=currentRecord.kind==='family'?['verify-diagnosis']:['verify-source','verify-page','verify-diagnosis'];
  const missing=needed.filter(id=>!$('#'+id).checked);
  document.querySelectorAll('.attest .check').forEach(l=>l.classList.toggle('missing',missing.includes(l.querySelector('input').id)));
  if(missing.length){notify('قبل الاعتماد علّم المربعات المظللة في أسفل النافذة.','error');return;}
 }
 if(button){button.disabled=true;if(e.target.id==='diagnose-form'){button.dataset.label=button.textContent;button.textContent='يجري التحليل…';}else button.classList.add('busy');}
 try{
 const id=e.target.id;
 if(id==='review-form'){
 const changes={},picked=el=>[...el.selectedOptions].map(x=>x.value);
 for(const key of ['title_ar','objection_text_ar','central_claim_ar','diagnostic_reason_ar','revealing_question_ar','treatment_ar','methodology_rule_ar','core_claim_ar','core_confusion_ar']){const el=$('#edit-'+key);if(changed(el))changes[key]=key==='title_ar'?el.value.replace(/\s*\n\s*/g,' ').trim():el.value;}
 for(const key of ['subclaims_ar','response_path_ar'])if(changed($('#edit-'+key)))changes[key]=$('#edit-'+key).value.split('\n').map(x=>x.trim()).filter(Boolean);
 if(changed($('#edit-compared_entities_ar')))changes.compared_entities_ar=$('#edit-compared_entities_ar').value.split('\n').filter(x=>x.trim()).map(x=>{const [a,b]=x.split('|');if(!a||!b)throw Error('اكتب طرفي المقارنة مفصولين بعلامة |');return {entity_a:a.trim(),entity_b:b.trim()};});
 if(changed($('#edit-pattern')))changes.primary_pattern=$('#edit-pattern').value;
 if(picked($('#edit-subpatterns')).join()!==editorStart.get('edit-subpatterns'))changes.sub_patterns=picked($('#edit-subpatterns'));
 if($('#edit-ruleids')&&picked($('#edit-ruleids')).join()!==editorStart.get('edit-ruleids'))changes.methodology_rule_ids=picked($('#edit-ruleids'));
 if(changed($('#edit-duplicate_group_id')))changes.duplicate_group_id=$('#edit-duplicate_group_id').value||null;
 if(changed($('#edit-family_id')))changes.family_id=$('#edit-family_id').value||null;
 if(changed($('#edit-similarity')))changes.similarity_type=$('#edit-similarity').value;
 await api('/records/'+currentRecord.id+'/review',{method:'POST',body:{expected_version:currentRecord.version,action:button.value,changes,notes:$('#edit-notes').value,source_verified:$('#verify-source').checked,page_verified:$('#verify-page').checked,diagnosis_verified:$('#verify-diagnosis').checked}});
 closeDialog($('#editor'));notify(button.value==='approve'?'اعتُمد السجل.':button.value==='reject'?'رُفض السجل.':'حُفظت التعديلات.');await render();
 }
 if(id==='profile-name-form'){const r=await api('/account',{method:'PATCH',body:{name:$('#profile-name').value}});showAccount({...me_,name:r.name});$('#profile-title').textContent=r.name;notify('حُفظ الاسم.');}
 if(id==='profile-email-form'){const problem=emailProblem($('#profile-email').value);if(problem)throw Error(problem);const r=await api('/account/email',{method:'POST',body:{email:$('#profile-email').value,password:$('#profile-email-password').value}});$('#profile-email-password').value='';notify('غُيّر البريد إلى '+r.email+'.');}
 if(id==='profile-password-form'){const problem=passwordProblem($('#profile-new').value,$('#profile-email')?.value||'');if(problem)throw Error(problem);await api('/account/password',{method:'POST',body:{current_password:$('#profile-current').value,new_password:$('#profile-new').value}});$('#profile-current').value='';$('#profile-new').value='';notify('غُيّرت كلمة المرور، وخرجت من الأجهزة الأخرى.');}
 if(id==='ingest-form'){const form=new FormData();form.append('file',$('#pdf-file').files[0]);form.append('title',$('#pdf-title').value);form.append('author',$('#pdf-author').value);form.append('profile',$('#pdf-profile').value);notify('يجري استخراج الصفحات، وقد يستغرق ذلك عدة دقائق.');const r=await api('/ingest',{method:'POST',body:form});notify('سجلات جديدة بانتظار المراجعة: '+num(r.candidate_count));await render();}
 if(id==='diagnose-form'){$('#diagnosis-result').innerHTML=loaderHtml('يجري التحليل، وقد يأخذ نصف دقيقة');const r=await api('/diagnose',{method:'POST',body:{text:$('#diagnose-text').value,include_drafts:$('#diagnose-drafts').checked}});$('#diagnosis-result').innerHTML=diagnosisHtml(r);refreshHistory().catch(()=>{});}
 if(id==='research-form'){const r=await api('/research',{method:'POST',body:{topic:$('#research-topic').value,limit:Number($('#research-limit').value)}});notify('حالات جديدة: '+num(r.record_ids.length)+'، ومصادر تعذر الوصول إليها: '+num(r.errors.length));await render();}
 if(id==='gate-form'){await api('/phase-two/enable',{method:'POST',body:{coverage_verified:$('#coverage-check').checked,notes:$('#coverage-notes').value}});notify('وُثّق اكتمال مراجعة الكتاب.');}
 if(id==='benchmark-form'){const ids=s=>$(s).value.split(/[\n,،]/).map(x=>x.trim()).filter(Boolean);await api('/benchmark',{method:'POST',body:{test_ids:ids('#test-ids'),validation_ids:ids('#validation-ids')}});notify('حُفظت مجموعة الاختبار.');await render();}
 if(id==='export-form'){const blob=await api('/export/'+$('#manifest').value,{method:'POST',blob:true});await download(blob,'manhaj-training.jsonl');await render();}
 }catch(err){notify(err.message,'error');if(e.target.id==='diagnose-form')$('#diagnosis-result').innerHTML='';}finally{if(button){button.disabled=false;button.classList.remove('busy');if(button.dataset.label){button.textContent=button.dataset.label;delete button.dataset.label;}}}
});
// Enter in the search box searches; Enter in a one-line review field must not trigger "approve".
document.addEventListener('change',e=>{if(e.target.closest('.attest .check')&&e.target.checked)e.target.closest('.check').classList.remove('missing');});
document.addEventListener('keydown',e=>{if(e.key!=='Enter')return;if(e.target.id==='search'){e.preventDefault();clearTimeout(searchTimer);query=e.target.value.trim();offset=0;render().catch(err=>notify(err.message));}else if(e.target.matches('#review-form input:not([type=checkbox]), #edit-title_ar'))e.preventDefault();});
init();
