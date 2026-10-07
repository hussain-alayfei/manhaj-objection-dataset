'use strict';
const $ = (s, root=document) => root.querySelector(s);
const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = n => Number(n||0).toLocaleString('en');
const titles = {overview:'نظرة عامة',analyze:'حلّل شبهة',profile:'الملف الشخصي',sources:'المصادر',objections:'شبهات الكتاب',external:'شبهات من مصادر أخرى',rules:'القواعد المنهجية',families:'الشبهات المتشابهة',review:'المراجعة',evaluation:'التقييم',export:'تصدير البيانات'};
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
// A notification drawn exactly as the alerts are (the same card, words and hairline), so every message the site
// shows looks alike: centred words and «حسنًا» under a hairline. It does not block the page and leaves by itself.
// It lives in the browser's top layer (popover), so it always shows above an open window.
function notify(message,kind='success'){
 const n=$('#notice');clearTimeout(noticeTimer);
 n.className='notice '+kind;n.setAttribute('role',kind==='error'?'alert':'status');
 // technical (non-Arabic) text never reaches the reader
 if(kind==='error'&&!/[؀-ۿ]/.test(message))message='حدث خطأ غير متوقع. حاول مرة أخرى.';
 n.innerHTML=`<div class="alert-body">${kind==='error'?'<h3>تعذّر ذلك</h3><p></p>':'<h3></h3>'}</div><div class="alert-actions one"><button type="button" class="notice-close">حسنًا</button></div>`;
 n.querySelector(kind==='error'?'p':'h3').textContent=message;
 n.classList.remove('leaving');
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
 // a one-letter conjunction or preposition stays joined to the quotation it opens: و«مائة عام»
 t=t.replace(/(^|\s)([وفبلك]) ([«﴿(])/g,'$1$2$3');
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
 let response;
 try{response=await fetch('/api'+path,{...options,headers});}
 catch{throw Error('تعذر الاتصال بالخادم. تحقق من الإنترنت ثم حاول مرة أخرى.');}
 if(!response.ok){let error;try{error=await response.json();}catch{error={detail:'تعذر إكمال الطلب'};}const failure=Error(typeof error.detail==='string'?error.detail:Array.isArray(error.detail)?'تحقق من البيانات المدخلة.':'تعذر إكمال الطلب');failure.status=response.status;if(response.status===401&&ready&&!path.startsWith('/auth/'))signedOut('انتهت الجلسة. سجّل الدخول من جديد.');throw failure;}
 if(options.blob)return response.blob();
 if(options.stream)return readStream(response,options.stream);
 // some actions (delete, sign out) answer with no body: that is success, not an error
 const body=await response.text();
 return body?JSON.parse(body):null;
}
// The live analysis answers with one JSON event per line; the last one carries the saved result.
async function readStream(response,onEvent){
 let result=null,buffer='';
 const handle=line=>{if(!line.trim())return;const event=JSON.parse(line);
  if(event.type==='result')result=event.data;
  else if(event.type==='error'){const failure=Error(event.detail||'تعذّر إكمال التحليل. حاول مرة أخرى.');failure.streamed=true;throw failure;}
  else if(event.type!=='ping')onEvent(event);};
 const reader=response.body?.getReader?.();
 if(!reader){(await response.text()).split('\n').forEach(handle);}
 else{const decoder=new TextDecoder();
  for(;;){const {value,done}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});
   let cut;while((cut=buffer.indexOf('\n'))>=0){handle(buffer.slice(0,cut));buffer=buffer.slice(cut+1);}}
  handle(buffer+decoder.decode());}
 if(!result){const failure=Error('انقطع الاتصال قبل اكتمال التحليل. إن اكتمل فستجده في سجل تحليلاتك.');failure.streamed=true;throw failure;}
 return result;
}
function title(name,subtitle,action=''){return `<div class="page-title"><div><h2>${esc(name)}</h2><p>${esc(subtitle)}</p></div>${action}</div>`;}
// Two faces: the public introduction for guests, the reviewing desk once signed in.
function setMode(mode){document.body.dataset.mode=mode;if(mode==='landing')document.title='مَنْهَج | مراجعة الشبهات';dispatchEvent(new Event('scroll'));}
async function init(){
 if(titles[location.hash.slice(1)])view=location.hash.slice(1);
 if(!token){setMode('landing');return;}
 setMode('app');
 try{const me=await api('/me');ready=true;taxonomy=me.taxonomy;caps=me.capabilities||{};showAccount(me);await render();prefetch();}
 catch(e){ready=false;if(e.status===401){signedOut(token?'انتهت الجلسة. سجّل الدخول من جديد.':'');return;}notify('تعذر الاتصال بالخادم. أعد تحميل الصفحة بعد قليل.','error');}
}
function signedOut(message){token='';remember.set('');ready=false;cache.clear();$('#content').innerHTML='';delete $('#content').dataset.view;document.querySelectorAll('dialog[open]').forEach(d=>d.close());setMode('landing');if(message)notify(message,'error');}
// ---------- Sidebar: a narrow rail when collapsed (remembered), a drawer on phones ----------
const phone=()=>window.matchMedia('(max-width: 760px)').matches;
const navPref={get(){try{return localStorage.getItem('manhaj-nav');}catch{return null;}},set(v){try{localStorage.setItem('manhaj-nav',v);}catch{}}};
function applyNav(){document.body.classList.toggle('nav-collapsed',!phone()&&navPref.get()==='collapsed');document.body.classList.remove('nav-open');$('#nav-toggle').setAttribute('aria-expanded',String(phone()?false:navPref.get()!=='collapsed'));}
document.querySelectorAll('#nav [data-view]').forEach(b=>b.title=b.textContent.trim());
$('#nav-toggle').addEventListener('click',()=>{if(phone()){const open=document.body.classList.toggle('nav-open');$('#nav-toggle').setAttribute('aria-expanded',String(open));}else{navPref.set(navPref.get()==='collapsed'?'open':'collapsed');applyNav();}});
$('#nav-backdrop').addEventListener('click',()=>document.body.classList.remove('nav-open'));
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.body.classList.contains('nav-open')){document.body.classList.remove('nav-open');$('#nav-toggle').setAttribute('aria-expanded','false');$('#nav-toggle').focus();}});
document.addEventListener('click',e=>{if(phone()&&e.target.closest('#nav [data-view], .brand'))document.body.classList.remove('nav-open');});
window.addEventListener('resize',applyNav);applyNav();

// ---------- Account: chip, menu, profile, sign out ----------
let me_={};
const initial=name=>(String(name||'؟').trim()[0]||'؟');
function showAccount(me){
 me_=me;const name=me.name||me.reviewer_id;
 document.querySelectorAll('[data-account-name]').forEach(x=>x.textContent=name+(caps.read_only?' (قراءة فقط)':''));
 document.querySelectorAll('[data-account-initial]').forEach(x=>paintAvatar(x,name,me.avatar));
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
 if(item.dataset.menu==='profile')go('profile');
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
// Profile: one calm page of grouped rows, as in Apple's settings. Each row opens a small sheet to edit.
function paintAvatar(el,name,avatar){
 el.textContent=avatar?'':initial(name);el.style.backgroundImage=avatar?`url("${avatar}")`:'';el.classList.toggle('has-photo',!!avatar);
}
async function profileView(){
 const seq=renderSeq;const p=await api('/account');if(stale(seq))return;
 const act=p.activity||{},since=p.created_at?new Date(p.created_at).toLocaleDateString('ar-u-nu-latn',{year:'numeric',month:'long',day:'numeric'}):'';
 const chev='<svg class="chev" width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" d="m15 6-6 6 6 6"/></svg>';
 $('#content').innerHTML=`<div class="profile-page">
  <section class="profile-hero"><span class="profile-photo" id="profile-photo" aria-hidden="true"></span>
   ${p.editable?`<div class="photo-actions"><button type="button" class="quiet" data-photo="pick">${p.avatar?'تغيير الصورة':'إضافة صورة'}</button>${p.avatar?'<button type="button" class="quiet danger-text" data-photo="remove">إزالة الصورة</button>':''}<input type="file" id="photo-input" accept="image/png,image/jpeg,image/webp" hidden></div>`:''}
   <h2>${esc(p.name)}</h2><p class="muted" dir="auto">${esc(p.email||(p.role==='admin'?'حساب مسؤول المشروع':''))}</p>${since?`<small class="muted">عضو منذ ${esc(since)}</small>`:''}</section>
  <h3 class="group-title">نشاطك</h3>
  <div class="group stats-row"><div><strong>${num(act.analyses||0)}</strong><span>تحليل</span></div><div><strong>${num(act.reviews||0)}</strong><span>مراجعة</span></div><div><strong>${num(act.approved||0)}</strong><span>اعتماد</span></div></div>
  ${p.editable?`<h3 class="group-title">المعلومات الشخصية</h3>
  <div class="group"><button type="button" class="group-row" data-edit="name"><span>الاسم</span><span class="value">${esc(p.name)}</span>${chev}</button><button type="button" class="group-row" data-edit="email"><span>البريد الإلكتروني</span><span class="value" dir="ltr">${esc(p.email)}</span>${chev}</button></div>
  <h3 class="group-title">الأمان</h3>
  <div class="group"><button type="button" class="group-row" data-edit="password"><span>كلمة المرور</span><span class="value">••••••••</span>${chev}</button></div>
  <p class="group-note">تغيير كلمة المرور يُخرجك من أجهزتك الأخرى.</p>`:`<p class="group-note">هذا حساب مسؤول المشروع، ولا تُعدَّل بياناته من هنا.</p>`}
  <div class="group"><button type="button" class="group-row destructive" data-menu="logout">تسجيل الخروج</button></div>
 </div>`;
 paintAvatar($('#profile-photo'),p.name,p.avatar);
}
// A sheet in Apple's manner: Cancel leads, the title sits in the middle, Save trails.
function editSheet({title,fields,save='حفظ',onSave}){
 const d=$('#sheet');
 d.innerHTML=`<form id="sheet-form"><header class="sheet-head"><button type="button" class="quiet" data-sheet="cancel">إلغاء</button><h3 id="sheet-title">${esc(title)}</h3><button class="quiet strong">${esc(save)}</button></header><div class="sheet-body">${fields.map(f=>`<label for="sheet-${f.id}">${esc(f.label)}</label><input id="sheet-${f.id}" type="${f.type||'text'}" value="${esc(f.value||'')}" ${f.dir?`dir="${f.dir}"`:''} autocomplete="${f.autocomplete||'off'}" required>`).join('')}${fields.some(f=>f.rules)?'<ul id="sheet-rules" class="pw-rules"><li data-rule="length">8 أحرف على الأقل</li><li data-rule="letter">حرف واحد على الأقل</li><li data-rule="digit">رقم واحد على الأقل</li></ul>':''}<p class="auth-error" id="sheet-error" hidden></p></div></form>`;
 d.querySelector('[data-sheet=cancel]').onclick=()=>closeDialog(d);
 d.querySelector('#sheet-form').onsubmit=async e=>{e.preventDefault();const btn=e.submitter;btn.disabled=true;btn.classList.add('busy');
  try{const values=Object.fromEntries(fields.map(f=>[f.id,$('#sheet-'+f.id).value]));await onSave(values);closeDialog(d);}
  catch(err){const box=$('#sheet-error');box.textContent=err.message;box.hidden=false;}
  finally{btn.disabled=false;btn.classList.remove('busy');}};
 d.showModal();d.querySelector('input')?.focus();
}
document.addEventListener('input',e=>{if(e.target.id==='sheet-new'){const c=passwordChecks(e.target.value);document.querySelectorAll('#sheet-rules li').forEach(li=>li.classList.toggle('ok',c[li.dataset.rule]));}});
document.addEventListener('click',async e=>{
 const edit=e.target.closest('[data-edit]'),photo=e.target.closest('[data-photo]');
 try{
 if(edit?.dataset.edit==='name')editSheet({title:'الاسم',fields:[{id:'name',label:'الاسم كما يظهر للمراجعين',value:me_.name,autocomplete:'name'}],onSave:async v=>{const r=await api('/account',{method:'PATCH',body:{name:v.name}});showAccount({...me_,name:r.name});notify('حُفظ الاسم.');render();}});
 if(edit?.dataset.edit==='email')editSheet({title:'البريد الإلكتروني',fields:[{id:'email',label:'البريد الجديد',type:'email',dir:'ltr',autocomplete:'email'},{id:'password',label:'كلمة المرور الحالية للتأكيد',type:'password',autocomplete:'current-password'}],onSave:async v=>{const problem=emailProblem(v.email);if(problem)throw Error(problem);const r=await api('/account/email',{method:'POST',body:{email:v.email,password:v.password}});notify('غُيّر البريد إلى '+r.email+'.');render();}});
 if(edit?.dataset.edit==='password')editSheet({title:'كلمة المرور',fields:[{id:'current',label:'كلمة المرور الحالية',type:'password',autocomplete:'current-password'},{id:'new',label:'كلمة المرور الجديدة',type:'password',autocomplete:'new-password',rules:true}],onSave:async v=>{const problem=passwordProblem(v.new,'');if(problem)throw Error(problem);await api('/account/password',{method:'POST',body:{current_password:v.current,new_password:v.new}});notify('غُيّرت كلمة المرور، وخرجت من أجهزتك الأخرى.');}});
 if(photo?.dataset.photo==='pick')$('#photo-input').click();
 if(photo?.dataset.photo==='remove'&&await confirmBox({title:'إزالة الصورة؟',message:'ستظهر الحرف الأول من اسمك بدلًا منها.',confirm:'إزالة',danger:true})){await api('/account/avatar',{method:'DELETE'});showAccount({...me_,avatar:null});notify('أُزيلت الصورة.');render();}
 }catch(err){notify(err.message,'error');}
});
// The picture is cropped to a square and resized to 256 px in the browser before it is sent.
document.addEventListener('change',async e=>{
 if(e.target.id!=='photo-input'||!e.target.files[0])return;
 try{
  const file=e.target.files[0];if(file.size>12*1024*1024)throw Error('الصورة كبيرة جدًا. اختر صورة أصغر من 12 ميغابايت.');
  const bmp=await createImageBitmap(file),side=Math.min(bmp.width,bmp.height),c=document.createElement('canvas');c.width=c.height=256;
  c.getContext('2d').drawImage(bmp,(bmp.width-side)/2,(bmp.height-side)/2,side,side,0,0,256,256);
  const blob=await new Promise(r=>c.toBlob(r,'image/webp',.86));const data=await new Promise(r=>{const fr=new FileReader();fr.onload=()=>r(fr.result);fr.readAsDataURL(blob);});
  await api('/account/avatar',{method:'POST',body:{image:data}});showAccount({...me_,avatar:data});notify('حُفظت الصورة.');render();
 }catch(err){notify(err.message||'تعذّر قراءة الصورة.','error');}finally{e.target.value='';}
});

// ---------- Sign up / sign in ----------
let authMode='signup';
function openAuth(mode){
 authMode=mode;const signup=mode==='signup';
 $('#auth-title').textContent=signup?'إنشاء حساب':'تسجيل الدخول';
 $('#auth-sub').textContent=signup?'اسمك وبريدك وكلمة مرور، ولا شيء غير ذلك.':'أهلًا بعودتك.';
 $('#name-field').hidden=!signup;$('#auth-name').required=signup;$('#pw-rules').hidden=!signup;
 document.querySelectorAll('#auth .field-error').forEach(n=>{n.hidden=true;n.previousElementSibling?.setAttribute('aria-invalid','false');});
 $('#auth-password').autocomplete=signup?'new-password':'current-password';
 $('#auth-password').type='password';document.querySelector('[data-pw-toggle]').setAttribute('aria-pressed','false');
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
document.addEventListener('click',e=>{const b=e.target.closest('[data-pw-toggle]');if(!b)return;const input=$('#auth-password'),shown=input.type==='password';
 input.type=shown?'text':'password';b.setAttribute('aria-pressed',String(shown));b.setAttribute('aria-label',shown?'إخفاء كلمة المرور':'إظهار كلمة المرور');input.focus({preventScroll:true});});
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
  else if(view==='profile')await profileView();
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
 const figures=[['المصادر',s.sources,'كتاب وليد'],['الشبهات',s.objections,'استُخرجت من نص الكتاب'],['القواعد المنهجية',s.rules,'تُراجع قبل استخدامها'],['بانتظار المراجعة',s.pending,s.approved?arCount(s.approved,['سجل واحد معتمد','سجلان معتمدان','سجلات معتمدة','سجلًا معتمدًا','سجل معتمد']):'لم يُعتمد شيء بعد']];
 // The page leads with analysing an objection; the queue and the method follow.
 $('#content').innerHTML=title('نظرة عامة','ما ينتظر المراجعة في المشروع الآن.')+
 `<section class="analyze-cta"><div><h3>حلّل شبهة</h3><p>اعرض الشبهة على أصول الكتاب، ليتبيّن موضع الالتباس فيها: أجمعٌ بين مختلفين هي أم تفريقٌ بين متماثلين، وما القاعدة التي يُرد بها عليها.</p></div><button class="primary big" data-go="analyze">ابدأ التحليل</button></section>
 <div class="metrics">${figures.map(([label,n,note])=>`<div class="metric"><div class="label">${label}</div><strong>${num(n)}</strong><small>${note}</small></div>`).join('')}</div>
 <div>
  <section class="card"><div class="card-head"><h3>بانتظار المراجعة</h3><button class="quiet" data-go="review">عرض الكل</button></div>${records.items.map(r=>`<div class="row"><div class="text"><h4>${esc(ar(r.title_ar))}</h4><p>${esc(where(r))}</p></div><button data-open="${esc(r.id)}">مراجعة</button></div>`).join('')||'<div class="empty">لا توجد حالات بانتظار المراجعة.</div>'}</section>

 </div>
 <section class="method-band" aria-labelledby="method-title"><div class="method-inner"><h3 id="method-title">كيف يفكر مَنْهَج حين تصله شبهة؟</h3><p>منهج لا يحفظ الأجوبة، بل يتتبع منشأ الشبهة ويفككها بالدليل، على أصل الكتاب: الشريعة لا تفرّق بين المتماثلات، ولا تجمع بين المختلفات.</p><ol class="path">${STEPS.map(x=>`<li${x.core?' class="core"':''}><small>${x.core?'قلب المنهج':x.ord.replace(' من إحدى عشرة','')}</small>${x.name}</li>`).join('')}</ol></div></section>`;
}
// ---------- Analyse an objection, with the reviewer's own history ----------
const when=iso=>iso?new Date(iso).toLocaleString('ar-u-nu-latn',{day:'numeric',month:'long',year:'numeric',hour:'numeric',minute:'2-digit'}):'';
// ---------- Analyses as conversations: the reader's analyses listed beside one open thread ----------
// A new thread asks for the objection; an open one shows the question, the analysis step by step, and the
// questions asked about it afterwards, answered from that analysis alone and written as they arrive.
const ICON_PLUS='<svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="2" d="M12 5v14M5 12h14"/></svg>';
const ICON_SEND='<svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" d="M12 19V5m-6 6l6-6l6 6"/></svg>';
const ICON_TRASH='<svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M4 7h16m-10 4v6m4-6v6M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg>';
const ICON_LIST='<svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/></g></svg>';
const EXAMPLES=['كيف يقول ﷺ: «سبعين خريفًا»، وفي حديث آخر: «مائة عام»؟ أليس هذا تناقضًا؟','كيف تُنفى رؤية الله بقوله تعالى: ﴿لا تدركه الأبصار﴾ وقد ثبتت في الآخرة؟','إذا كان الله قدّر المعصية، فلماذا يُحاسَب عليها العبد؟'];
let chatActive=null,chatItems=[],chatDrafts=false;
function dayGroup(iso){
 const d=new Date(iso),t=new Date(),days=Math.round((new Date(t.getFullYear(),t.getMonth(),t.getDate())-new Date(d.getFullYear(),d.getMonth(),d.getDate()))/864e5);
 return days<=0?'اليوم':days===1?'أمس':days<7?'آخر سبعة أيام':days<30?'آخر ثلاثين يومًا':'أقدم';
}
function chatItem(d){
 const state=d.abstention_reason?'<span class="pill pending">لم يُصنَّف</span>':d.primary_pattern?`<span class="pill">${esc(patternName(d.primary_pattern))}</span>`:'';
 const flags=(d.mode==='draft'?'<span class="pill draft">مسودة</span>':'')+(d.feedback?.verdict==='wrong'?'<span class="pill rejected">أُبلغ عن خطأ</span>':'');
 const on=d.id===chatActive;
 return `<div class="chat-item${on?' active':''}" data-chat="${esc(d.id)}"><button type="button" class="chat-open" data-diag="${esc(d.id)}"${on?' aria-current="true"':''}><span class="chat-title">${esc(ar(d.input_ar))}</span><span class="chat-meta">${state}${flags}</span></button><button type="button" class="chat-del" data-delete-one="${esc(d.id)}" aria-label="حذف هذا التحليل" title="حذف">${ICON_TRASH}</button></div>`;
}
function drawChatList(total){
 const box=$('#chat-items');if(!box)return;
 if(!chatItems.length){box.innerHTML='<p class="chat-none">لا تحليلات بعد. ستظهر هنا كل شبهة تحلّلها.</p>';$('#history-more').hidden=true;return;}
 let html='',group='';
 for(const d of chatItems){const g=dayGroup(d.created_at);if(g!==group){html+=`<h4 class="chat-group" data-key="g:${g}">${g}</h4>`;group=g;}html+=chatItem(d);}
 // Redrawn in place: each row that stays glides from where it was, a new one fades in at its place, and the first
 // drawing of the list simply fades in
 const keyOf=x=>x.dataset.key||x.dataset.chat,first=!box.querySelector('[data-key],[data-chat]');
 const was=new Map([...box.children].filter(keyOf).map(x=>[keyOf(x),x.getBoundingClientRect().top]));
 box.innerHTML=html;$('#history-more').hidden=chatItems.length>=total;
 if(calm()||!box.animate)return;
 if(first){box.animate([{opacity:0},{opacity:1}],{duration:280,easing:'ease-out'});return;}
 for(const x of box.children){const before=was.get(keyOf(x));
  if(before===undefined){x.animate([{opacity:0,transform:'translateY(-6px)'},{opacity:1,transform:'none'}],{duration:420,delay:120,easing:'cubic-bezier(.2,.8,.2,1)',fill:'backwards'});continue;}
  const dy=before-x.getBoundingClientRect().top;
  if(Math.abs(dy)>1)x.animate([{transform:`translateY(${dy}px)`},{transform:'none'}],{duration:380,easing:'cubic-bezier(.2,.8,.2,1)'});}
}
async function refreshHistory(append=false){
 if(!$('#chat-items'))return;
 const data=await api(`/diagnoses?limit=30&offset=${append?chatItems.length:0}`);
 chatItems=append?[...chatItems,...data.items]:data.items;drawChatList(data.total);
}
function markActive(){
 document.querySelectorAll('.chat-item').forEach(x=>{const on=x.dataset.chat===chatActive,b=x.querySelector('.chat-open');x.classList.toggle('active',on);if(on)b.setAttribute('aria-current','true');else b.removeAttribute('aria-current');});
}
async function analyzeView(){
 const seq=renderSeq;
 const s=await api('/summary').catch(()=>({rules_approved:0}));
 if(stale(seq))return;
 chatDrafts=!s.rules_approved; // with no approved rules yet, the book's candidate rules are the only useful source
 $('#content').innerHTML=`<div class="chat" id="chat"><aside class="chat-list" id="chat-list" aria-label="سجل التحليلات"><div class="chat-list-head"><h3>التحليلات</h3><button type="button" class="chat-toggle" data-chat-list aria-controls="chat-list" aria-expanded="true">${ICON_LIST}</button></div><button type="button" class="chat-new" data-chat-new title="تحليل جديد">${ICON_PLUS}<span>تحليل جديد</span></button><div class="chat-items" id="chat-items" role="navigation" aria-label="سجل تحليلاتك"></div><button type="button" class="quiet chat-more" id="history-more" hidden>عرض المزيد</button></aside><div class="chat-split" role="separator" tabindex="0" aria-orientation="vertical" aria-controls="chat-list" aria-valuemin="0" aria-valuemax="440" aria-label="عرض قائمة التحليلات: اسحب لتوسيعها أو تضييقها، وانقر مرتين لإرجاعها" title="اسحب لتغيير عرض القائمة، وانقر مرتين لإرجاعها"></div><button type="button" class="chat-scrim" data-chat-list tabindex="-1" aria-label="إغلاق قائمة التحليلات"></button><section class="thread" id="thread"></section></div>`;
 const saved=listWidth.get();setListWidth(saved<0?0:saved||LIST_DEFAULT,false);
 showThread(chatActive).catch(err=>notify(err.message,'error'));
 try{await refreshHistory();}catch(err){if(!stale(seq))$('#chat-items').innerHTML=`<p class="chat-none">${esc(err.message)}</p>`;}
}
// The line between the list and the thread: drag it to widen or narrow the list, or past its edge to fold it into a
// slim rail; a double click (or Enter) brings back the usual width. The list's own button folds and unfolds it in
// place, so the control and the list always stand on the same side. The choice is remembered on this device
// (a negative number keeps the width a folded list will open to).
const LIST_MIN=200,LIST_MAX=440,LIST_DEFAULT=250;
const listWidth={get(){try{return Number(localStorage.getItem('manhaj-chat-w'))||0;}catch{return 0;}},set(v){try{localStorage.setItem('manhaj-chat-w',String(v));}catch{}},
 open(){const v=Math.abs(this.get());return v>=LIST_MIN&&v<=LIST_MAX?v:LIST_DEFAULT;}};
const drawerMode=()=>matchMedia('(max-width:1280px)').matches;
function setListWidth(w,save=true){
 const chat=$('#chat');if(!chat)return;
 const folded=w<LIST_MIN*.7,width=folded?0:Math.round(Math.min(LIST_MAX,Math.max(LIST_MIN,w)));
 if(!folded)chat.style.setProperty('--list-w',width+'px');
 chat.classList.toggle('list-folded',folded);
 chat.querySelector('.chat-split')?.setAttribute('aria-valuenow',String(width));
 if(save)listWidth.set(folded?-listWidth.open():width);
 labelListToggle();
}
const listNow=()=>{const chat=$('#chat');return chat.classList.contains('list-folded')?0:parseInt(getComputedStyle(chat).getPropertyValue('--list-w'))||LIST_DEFAULT;};
// The list's button says what it will do: show or hide on a wide screen, open or close the drawer on a narrow one
function labelListToggle(){
 const chat=$('#chat');if(!chat)return;
 const shown=drawerMode()?chat.classList.contains('list-open'):!chat.classList.contains('list-folded');
 chat.querySelectorAll('[data-chat-list]:not(.chat-scrim)').forEach(b=>{
  const label=drawerMode()?(shown?'إغلاق قائمة التحليلات':'فتح قائمة التحليلات'):(shown?'إخفاء قائمة التحليلات':'إظهار قائمة التحليلات');
  b.setAttribute('aria-expanded',String(shown));if(b.classList.contains('chat-toggle')){b.setAttribute('aria-label',label);b.title=label;}});
}
function setDrawer(open,{focus=true}={}){
 const chat=$('#chat');if(!chat||chat.classList.contains('list-open')===open)return;
 chat.classList.toggle('list-open',open);labelListToggle();
 if(!focus)return;
 if(open)setTimeout(()=>$('#chat-list .chat-toggle')?.focus({preventScroll:true}),60);
 else $('#thread .thread-list-btn')?.focus({preventScroll:true});
}
function toggleList(){
 const chat=$('#chat');if(!chat)return;
 if(drawerMode()){setDrawer(!chat.classList.contains('list-open'));return;}
 setListWidth(chat.classList.contains('list-folded')?listWidth.open():0);
}
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('#chat')?.classList.contains('list-open')){e.preventDefault();setDrawer(false);}});
addEventListener('resize',()=>{if(!drawerMode())$('#chat')?.classList.remove('list-open');labelListToggle();});
document.addEventListener('pointerdown',e=>{
 const split=e.target.closest?.('.chat-split');if(!split||e.button!==0)return;
 e.preventDefault();split.setPointerCapture(e.pointerId);split.classList.add('dragging');document.body.classList.add('resizing');
 const at=ev=>ev.clientX-$('#chat').getBoundingClientRect().left; // the list sits on the left (end) side
 const move=ev=>setListWidth(at(ev),false);
 const up=ev=>{split.classList.remove('dragging');document.body.classList.remove('resizing');for(const [t,f] of [['pointermove',move],['pointerup',up],['pointercancel',up]])split.removeEventListener(t,f);setListWidth(at(ev));};
 split.addEventListener('pointermove',move);split.addEventListener('pointerup',up);split.addEventListener('pointercancel',up);
});
document.addEventListener('dblclick',e=>{if(e.target.closest?.('.chat-split'))setListWidth(LIST_DEFAULT);});
document.addEventListener('keydown',e=>{
 if(!e.target.closest?.('.chat-split'))return;
 if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();const wider=e.key==='ArrowRight',now=listNow();setListWidth(now===0?(wider?LIST_MIN:0):now+(wider?24:-24));}
 if(e.key==='Enter'||e.key===' '){e.preventDefault();setListWidth(listNow()?0:listWidth.open());}
});
const threadTop=open=>`<header class="thread-head">${open?'<button type="button" class="thread-new-btn" data-chat-new>'+ICON_PLUS+'<span>تحليل جديد</span></button>':''}<button type="button" class="thread-list-btn" data-chat-list aria-controls="chat-list" aria-expanded="false">${ICON_LIST}<span>التحليلات</span></button></header>`;
function newThreadHtml(){
 return `${threadTop(false)}<div class="thread-new"><img src="/static/img/emblem.webp" alt="" width="52" height="52"><h2>ما الشبهة التي تريد تحليلها؟</h2><p>يحلّلها مَنْهَج في إحدى عشرة خطوة، من تحرير الدعوى إلى جواب موثّق بمصادره، ثم تسأله عمّا تشاء في تحليله.</p>
 <form id="diagnose-form" class="composer big"><label for="diagnose-text" class="sr-only">نص الشبهة</label><textarea id="diagnose-text" rows="3" required maxlength="12000" placeholder="اكتب الشبهة هنا…"></textarea>
  <div class="composer-bar"><fieldset class="segmented small"><legend class="sr-only">القواعد المستعملة في التحليل</legend><label><input type="radio" name="rules-source" value="approved" ${chatDrafts?'':'checked'}><span>القواعد المعتمدة</span></label><label><input type="radio" name="rules-source" value="all" ${chatDrafts?'checked':''}><span>كل قواعد الكتاب</span></label></fieldset><button class="primary send" id="diagnose-submit" aria-label="حلّل الشبهة">${ICON_SEND}<span>حلّل</span></button></div></form>
 <div class="thread-try"><h4>أمثلة تجرّبها</h4>${EXAMPLES.map(x=>`<button type="button" data-example="${esc(x)}">${esc(x)}</button>`).join('')}</div>
 <p class="ai-note">النتيجة اقتراح آلي يعين على البحث، وليست فتوى ولا حكمًا، ولا تُعتمد قبل أن يراجعها مختص.${chatDrafts?' ولم تُعتمد قواعد بعد، فيستعين التحليل بقواعد الكتاب قبل مراجعتها، وتُعلَّم النتيجة «مسودة».':''}</p></div>`;
}
const turnHtml=t=>`<div class="msg me"><p>${esc(t.question)}</p></div><div class="msg bot"><div class="md">${md(t.answer)}</div></div>`;
function askHtml(did){
 return `<form id="ask-form" class="composer ask" data-did="${esc(did||'')}"><label for="ask-text" class="sr-only">سؤالك عن التحليل</label><textarea id="ask-text" rows="1" maxlength="2000" required placeholder="${did?'اسأل عن هذا التحليل…':'تستطيع السؤال حين يكتمل التحليل'}"${did?'':' disabled'}></textarea><button class="primary send" aria-label="أرسل السؤال"${did?'':' disabled'}>${ICON_SEND}</button></form><p class="composer-note">يجيب من هذا التحليل ومصادره فقط، ولا يُصدر فتوى.</p>`;
}
function conversationHtml(input,did){
 return `${threadTop(true)}<div class="thread-body"><div class="msg me"><p>${esc(ar(input))}</p></div><div class="msg bot analysis"><section class="method" data-method></section><div data-after></div></div><div class="turns" id="turns"></div></div><div class="thread-foot">${askHtml(did)}</div>`;
}
// Moving between analyses reads as one motion: the open thread fades away, the next one fades in rising a little.
// Only opacity and transform change, so the graphics card draws it without repainting the page.
let threadSeq=0;
// a motion is never waited on for longer than it should take (a hidden tab does not run animations)
const settled=(anim,ms)=>Promise.race([anim.finished.catch(()=>{}),new Promise(r=>setTimeout(r,ms))]);
function threadOut(thread){
 thread.getAnimations().forEach(a=>a.cancel());
 if(calm()||!thread.firstElementChild||!thread.animate)return Promise.resolve();
 return settled(thread.animate([{opacity:1},{opacity:0}],{duration:140,easing:'cubic-bezier(.4,0,1,1)',fill:'forwards'}),200);
}
function threadIn(thread){
 thread.getAnimations().forEach(a=>a.cancel());
 if(!calm()&&thread.animate)thread.animate([{opacity:0,transform:'translateY(10px)'},{opacity:1,transform:'none'}],{duration:360,easing:'cubic-bezier(.2,.8,.2,1)'});
}
// One analysis in the thread, or a new one when no id is given; the list marks the open one
async function showThread(id){
 const thread=$('#thread');if(!thread)return;
 const ticket=++threadSeq,first=!thread.firstElementChild,arrive=()=>{if(first)thread.getAnimations().forEach(a=>a.cancel());else threadIn(thread);};
 chatActive=id||null;markActive();setDrawer(false,{focus:false});
 const loading=id?api('/diagnoses/'+id):null;loading?.catch(()=>{}); // its error is shown once, below
 await threadOut(thread);
 const current=()=>ticket===threadSeq&&thread.isConnected;
 if(!current())return;
 if(!id){thread.innerHTML=newThreadHtml();arrive();$('#diagnose-text')?.focus({preventScroll:true});scrollTo(0,0);return;}
 // a placeholder only when the analysis is slow to come, so a quick switch never flashes one
 const slow=setTimeout(()=>{if(!current())return;thread.innerHTML=`${threadTop(true)}<div class="thread-body"><div class="writing" role="status"><p>يُفتح التحليل…</p><i></i><i></i><i></i></div></div>`;threadIn(thread);},180);
 // whatever happens the thread comes back into view: the analysis, or a plain word on why it did not open
 try{
  const r=await loading;clearTimeout(slow);
  if(!current()||chatActive!==id)return;
  thread.innerHTML=conversationHtml(r.input_ar,r.method?r.id:'');
  const bot=thread.querySelector('.msg.bot.analysis');
  if(r.method){mountMethod(bot.querySelector('[data-method]'),methodFromResult(r));bot.querySelector('[data-after]').innerHTML=feedbackHtml(r);}
  else bot.innerHTML=diagnosisHtml(r);
  $('#turns').innerHTML=(r.conversation||[]).map(turnHtml).join('');
 }catch(err){
  clearTimeout(slow);if(!current())return;
  thread.innerHTML=`${threadTop(true)}<div class="thread-body"><div class="thread-error" role="alert"><h3>تعذّر فتح هذا التحليل</h3><p>${esc(/[؀-ۿ]/.test(err?.message||'')?err.message:'حدث خطأ غير متوقع.')}</p><button type="button" data-diag="${esc(id)}">حاول مرة أخرى</button></div></div>`;
 }
 arrive();scrollTo(0,0);
}
async function openAnalysis(id){
 chatActive=id;
 if(view!=='analyze'){location.hash='analyze';return;}
 await showThread(id);
}
// Answers arrive as markdown: headings, lists, quotes, bold and links, drawn safely (the text is escaped first)
function md(src){
 const inline=s=>esc(s).replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>').replace(/(^|[\s(«])\*(?!\s)([^*]+?)\*(?=[\s).،,:؛»]|$)/g,'$1<em>$2</em>')
  .replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\[([^\]]+)\]\((https:\/\/[^\s)]+)\)/g,'<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
 let html='',list=null,para=[],quote=[];
 const closePara=()=>{if(para.length){html+=`<p>${para.map(inline).join('<br>')}</p>`;para=[];}};
 const closeQuote=()=>{if(quote.length){html+=`<blockquote>${quote.map(inline).join('<br>')}</blockquote>`;quote=[];}};
 const closeList=()=>{if(list){html+=`</${list}>`;list=null;}};
 const closeAll=()=>{closePara();closeQuote();closeList();};
 for(const raw of String(src||'').replace(/\r/g,'').split('\n')){
  const line=raw.replace(/\s+$/,'');let m;
  if(!line.trim()){closeAll();continue;}
  if((m=line.match(/^\s*#{1,6}\s+(.*)$/))){closeAll();html+=`<h4>${inline(m[1])}</h4>`;continue;}
  if(/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)){closeAll();html+='<hr>';continue;}
  if((m=line.match(/^\s*>\s?(.*)$/))){closePara();closeList();quote.push(m[1]);continue;}
  if((m=line.match(/^\s*[-*•]\s+(.*)$/))||(m=line.match(/^\s*(?:\d+|[٠-٩]+)[.)]\s+(.*)$/))){
   const kind=/^\s*[-*•]/.test(line)?'ul':'ol';closePara();closeQuote();
   if(list!==kind){closeList();html+=`<${kind}>`;list=kind;}
   html+=`<li>${inline(m[1])}</li>`;continue;}
  closeQuote();closeList();para.push(line.trim());
 }
 closeAll();return html;
}
const fit=t=>{t.style.height='auto';t.style.height=Math.min(t.scrollHeight,240)+'px';};
document.addEventListener('input',e=>{if(e.target.matches?.('.composer textarea'))fit(e.target);});
// Enter sends, Shift+Enter starts a new line (as in a chat)
document.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing&&e.target.matches?.('.composer textarea')){e.preventDefault();const f=e.target.form;if(e.target.value.trim())f.requestSubmit(f.querySelector('button.send'));}});
// Tabs that open only after expert review say so plainly, with the progress so far and the next step.
function gateHtml({heading,why,steps,s,note=''}){
 const approvedObjections=s.objections_approved??0,approvedRules=s.rules_approved??0;
 return `<section class="gate"><h3>${heading}</h3><p>${why}</p><ol>${steps.map(x=>`<li>${x}</li>`).join('')}</ol>
  <div class="gate-progress"><div><strong>${num(s.approved||0)}</strong><span>سجل معتمد</span></div><div><strong>${num(s.pending||0)}</strong><span>بانتظار المراجعة</span></div><div><strong>${num(approvedRules)}</strong><span>قاعدة معتمدة</span></div></div>
  <div class="gate-foot"><button class="primary" data-go="review">ابدأ المراجعة</button>${note?`<p>${note}</p>`:''}</div></section>`;
}
async function recordsView(){
 const seq=renderSeq;
 const chosen=status===null?(view==='review'?'needs_review':''):status;
 const data=await api(recordsPath(view,offset,query,chosen));
 if(!data.items.length&&offset>0&&offset>=data.total){offset=Math.max(0,Math.ceil(data.total/30)*30-30);return render();}
 let extra='';
 if(view==='external'&&!data.total&&!query&&!chosen){const s=await api('/summary');if(stale(seq))return;extra=gateHtml({s,heading:'شبهات من مواقع موثوقة خارج الكتاب',
  why:'تُجمع هنا شبهات شائعة من مواقع موثوقة، وتُحلَّل بمنهج الكتاب وتدخل المراجعة. ولا يبدأ جمعها قبل أن تُحكم شبهات الكتاب نفسه، لأنها الأساس الذي تُقاس عليه.',
  steps:['يراجع المختصون شبهات الكتاب وقواعده ويعتمدون الصحيح منها.','يوثّق المسؤول اكتمال مراجعة الكتاب.','تُراجَع حقوق كل موقع قبل جمع نصوصه، ثم يبدأ الجمع.'],note:'وإلى ذلك الحين يستعين كل تحليل بالمكتبة الشاملة وبمواقع موثوقة على الإنترنت.'});
  $('#content').dataset.view=view;$('#content').innerHTML=title(titles[view],'لم تُضف شبهات من خارج الكتاب بعد.')+extra;return;}
 else if(view==='external')extra=!caps.heavy_jobs?'<p class="lead-note">يضيفها مسؤول المشروع من مصادر موثوقة، وتظهر هنا لتراجعها.</p>':`<div class="banner">يبدأ جمع الشبهات من مصادر أخرى بعد إنهاء مراجعة الكتاب كاملًا، وكل نتيجة تدخل قائمة المراجعة.</div><details class="card spaced"><summary>البحث في المصادر المسموح بها</summary><form id="research-form"><label for="research-topic">الموضوع</label><input id="research-topic" required><label for="research-limit">أقصى عدد من النتائج</label><input id="research-limit" type="number" min="1" max="50" value="5"><button class="primary spaced">ابحث</button></form><form id="gate-form"><label class="check"><input id="coverage-check" type="checkbox" required>أشهد بأن مراجعة جميع شبهات الكتاب وقواعده اكتملت.</label><label for="coverage-notes">ملاحظات المراجعة</label><textarea id="coverage-notes" required></textarea><button class="spaced">توثيق اكتمال مراجعة الكتاب</button></form></details>`;
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
// Arabic counted nouns: 1 and 2 have their own forms, 3-10 take the plural, 11-99 the accusative singular,
// round hundreds the genitive singular (applied to the last two digits, as written Arabic does).
function arCount(n,[one,two,few,many,hundred]){
 if(n===1)return one;if(n===2)return two;const r=n%100;
 return `${num(n)} ${r>=3&&r<=10?few:r>=11?many:hundred}`;
}
const countLabel=n=>n===0?'لا سجلات':arCount(n,['سجل واحد','سجلان','سجلات','سجلًا','سجل']);
function tableHtml(data){
 const last=Math.min(offset+30,data.total);
 return `<div class="table-wrap"><table><thead><tr><th>العنوان</th><th>التشخيص</th><th>المصدر</th><th>الحالة</th><th><span class="sr-only">إجراء</span></th></tr></thead><tbody>${data.items.map(r=>`<tr><td>${esc(ar(r.title_ar))}</td><td>${esc(patternName(r.primary_pattern))}<small>${esc(r.sub_patterns.map(subName).join('، '))}</small></td><td>${esc(r.source?.source_name||'مجموعة مقترحة')}<small>${esc(page(r))}</small></td><td>${badge(r.review_status)}</td><td><button data-open="${esc(r.id)}">فتح</button></td></tr>`).join('')}</tbody></table>${data.items.length?'':`<div class="empty">${query?'لا شيء يطابق «'+esc(query)+'».':'القائمة فارغة.'}</div>`}</div>${data.total>30?`<div class="pagination"><span>${num(offset+1)} إلى ${num(last)} من ${num(data.total)}</span><div><button data-page="prev" ${offset===0?'disabled':''}>السابق</button> <button data-page="next" ${offset+30>=data.total?'disabled':''}>التالي</button></div></div>`:''}`;
}
// Results follow the search box as you type (after a short pause) and the status list at once.
let searchTimer;
document.addEventListener('input',e=>{if(e.target.id!=='search')return;clearTimeout(searchTimer);searchTimer=setTimeout(()=>{query=e.target.value.trim();offset=0;render().catch(err=>notify(err.message,'error'));},280);});
document.addEventListener('change',e=>{if(e.target.id!=='status-filter')return;status=e.target.value;offset=0;render().catch(err=>notify(err.message,'error'));});
async function sourcesView(){
 const seq=renderSeq;
 const sources=await api('/sources');
 if(stale(seq))return;
 $('#content').innerHTML=title('المصادر','الكتب التي استُخرجت منها الشبهات والقواعد.')+`<div class="list-stack">${sources.map(s=>`<article class="card source-card"><img class="book-cover" src="/static/img/book-cover.webp" alt="" width="72" height="96"><div class="text"><h3>${esc(s.source_name)}</h3><p>${esc([s.actual_title,s.author].filter(Boolean).join('، '))}</p><p>${s.page_count?num(s.page_count)+' صفحة':''}</p></div><div class="source-actions"><button class="primary" data-book="${esc(s.id)}" data-bookpage="1" data-booktitle="${esc(s.source_name)}">اقرأ الكتاب</button><button data-chunks="${esc(s.id)}">النص المستخرج</button></div></article>`).join('')}</div>${!caps.heavy_jobs?'<p class="lead-note spaced">لإضافة كتاب جديد تواصل مع مسؤول المشروع.</p>':`<details class="card spaced"><summary>إضافة كتاب PDF</summary><form id="ingest-form"><label for="pdf-title">اسم الكتاب</label><input id="pdf-title" value="كتاب وليد" required><label for="pdf-author">المؤلف كما يظهر في الكتاب</label><input id="pdf-author"><label for="pdf-profile">طريقة ترتيب النص</label><select id="pdf-profile"><option value="standard">عادية</option><option value="rtl_visual">حروف معكوسة الترتيب (مثل الكتاب الحالي)</option></select><label for="pdf-file">ملف PDF</label><input id="pdf-file" type="file" accept="application/pdf" required><button class="primary spaced">استخراج إلى قائمة المراجعة</button></form></details>`}`;
}
async function evaluationView(){
 const seq=renderSeq;
 const [manifests,runs,s]=await Promise.all([api('/documents/dataset_manifests'),api('/documents/evaluation_runs'),api('/summary')]);
 if(stale(seq))return;
 if(!manifests.length&&!runs.length&&!s.approved){$('#content').innerHTML=title('التقييم','نختبر دقة التحليل على حالات معتمدة لم يرها النظام من قبل.')+gateHtml({s,heading:'يبدأ التقييم بعد اعتماد الحالات',
  why:'يقيس التقييم دقة التحليل بمقارنته بحالات اعتمدها المختصون ولم يرها النظام. ولا يصح قياسه على حالات لم يراجعها أحد.',
  steps:['يعتمد المختصون عشرين شبهة على الأقل وخمس قواعد من الكتاب.','تُختار منها مجموعة اختبار تُحجب عن التحليل.','يُحلَّل كل اختبار ويُقارن بالجواب المعتمد، فتظهر النتائج هنا.']});return;}
 $('#content').innerHTML=title('التقييم','نختبر دقة التحليل على حالات معتمدة لم يرها النظام من قبل.')+`<div class="two-col"><section class="card"><h3>إنشاء مجموعة اختبار</h3><form id="benchmark-form"><label for="test-ids">أرقام حالات الاختبار المعتمدة (سطر لكل حالة)</label><textarea id="test-ids" required dir="ltr"></textarea><label for="validation-ids">أرقام حالات التحقق (اختياري)</label><textarea id="validation-ids" dir="ltr"></textarea><button class="primary spaced">حفظ المجموعة</button></form></section><section class="card"><h3>المجموعات المحفوظة</h3>${manifests.map(m=>`<div class="row"><div><small>${esc(when(m.payload.created_at))}</small><p>تدريب ${num(m.payload.training_ids.length)}، تحقق ${num(m.payload.validation_ids.length)}، اختبار ${num(m.payload.test_ids.length)}</p></div></div>`).join('')||'<div class="empty">لا توجد مجموعات بعد.</div>'}</section></div><section class="card spaced"><h3>نتائج التقييم</h3>${runs.map(r=>`<details><summary>تقييم ${esc(when(r.payload.at))}</summary>${metricsTable(r.payload.metrics)}</details>`).join('')||'<div class="empty">لم يُجرَ تقييم بعد.</div>'}</section>`;
}
const metricNames={primary_pattern_accuracy:'دقة التشخيص الرئيس',sub_pattern_accuracy:'دقة تفصيل التشخيص',human_review_trigger_accuracy:'دقة طلب مراجعة المختص',duplicate_family_detection_accuracy:'دقة كشف الشبهات المتشابهة',central_claim_accuracy:'دقة تحرير الدعوى',objection_decomposition_accuracy:'دقة تفكيك الشبهة',source_grounding_accuracy:'الاستناد إلى نص الكتاب',citation_accuracy:'دقة الإحالة إلى الصفحات',unsupported_diagnosis_rate:'نسبة التشخيص غير المؤسس'};
const metricsTable=m=>`<table class="metrics-table"><tbody>${Object.entries(m||{}).map(([k,v])=>`<tr><th>${esc(metricNames[k]||k)}</th><td>${v.value==null?'لم يُقس بعد':num(Math.round(v.value*100))+'%'}</td><td class="muted">${v.rated_count?arCount(v.rated_count,['حالة واحدة','حالتان','حالات','حالةً','حالة']):''}</td></tr>`).join('')}</tbody></table>`;
async function exportView(){
 const seq=renderSeq;
 const [manifests,exports,s]=await Promise.all([api('/documents/dataset_manifests'),api('/documents/training_exports'),api('/summary')]);
 if(stale(seq))return;
 if(!manifests.length&&!exports.length&&!s.approved){$('#content').innerHTML=title('تصدير البيانات','تُصدَّر الحالات المعتمدة فقط، وتُستبعد حالات الاختبار.')+gateHtml({s,heading:'يُتاح التصدير بعد الاعتماد',
  why:'التصدير يخرج الحالات المعتمدة وحدها، بنصوصها وتشخيصها ومصادرها، لتُستعمل في تدريب النماذج أو في النشر. ولم يُعتمد بعد شيء يصلح للتصدير.',
  steps:['يعتمد المختصون الشبهات والقواعد بعد مراجعتها.','تُحفظ مجموعة اختبار في صفحة التقييم.','ينزّل المسؤول ملف التدريب أو كل السجلات المعتمدة من هنا.']});return;}
 $('#content').innerHTML=title('تصدير البيانات','تُصدَّر الحالات المعتمدة فقط، وتُستبعد حالات الاختبار.')+`<div class="two-col"><section class="card"><h3>ملف التدريب</h3><form id="export-form"><label for="manifest">مجموعة البيانات</label><select id="manifest" required><option value="">اختر مجموعة</option>${manifests.map(m=>`<option value="${esc(m.id)}">مجموعة ${esc(when(m.payload.created_at))} (${num(m.payload.training_ids.length)} حالة تدريب)</option>`).join('')}</select><button class="primary spaced">تنزيل ملف التدريب</button></form><button data-action="json-export" class="spaced">تنزيل كل السجلات المعتمدة</button></section><section class="card"><h3>عمليات التصدير السابقة</h3>${exports.map(x=>`<div class="row"><div><small>${esc(new Date(x.payload.at).toLocaleString('ar-u-nu-latn'))}</small><p>${num(x.payload.records_count??0)} حالة</p></div></div>`).join('')||'<div class="empty">لا توجد عمليات تصدير.</div>'}</section></div>`;
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
 $('#editor-content').innerHTML=`<header class="modal-head"><div class="modal-title"><h3 id="editor-title">مراجعة ${kindName}</h3>${badge(r.review_status)}<small class="muted">الإصدار ${num(r.version)}</small></div><button data-action="close">إغلاق</button></header>
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

// ---------- The method: how Manhaj thinks when an objection arrives ----------
// Eleven steps and, between the sixth and the seventh, the two governing rules. The analysis streams in,
// so each step shows the moment it is written. One step at a time in the middle, reached in order; the answer last.
const BOOK='كتاب «تربية الملكة على كشف الشبهة» للشيخ وليد بن راشد السعيدان';
const STEPS=[
 {key:'step1_framing',mark:'1',ord:'الخطوة الأولى من إحدى عشرة',name:'تحرير الشبهة',tag:'تحويل كلام السائل إلى بنية منطقية واضحة'},
 {key:'step2_entities',mark:'2',ord:'الخطوة الثانية من إحدى عشرة',name:'استخراج الكيانات والأدلة',tag:'كل ما تقوم عليه الشبهة… مستخرَج ومصنَّف'},
 {key:'step3_sources',mark:'3',ord:'الخطوة الثالثة من إحدى عشرة',name:'التحقق من المصادر',tag:'لا جواب يُبنى على نص لا يثبت'},
 {key:'step4_related',mark:'4',ord:'الخطوة الرابعة من إحدى عشرة',name:'جمع النصوص ذات الصلة',tag:'اجمع قبل أن تحكم'},
 {key:'step5_language',mark:'5',ord:'الخطوة الخامسة من إحدى عشرة',name:'التحليل اللغوي والدلالي',tag:'اللفظ كما فهمه العرب زمن النص'},
 {key:'step6_comparison',mark:'6',ord:'الخطوة السادسة من إحدى عشرة',name:'المقارنة الدلالية',tag:'هل النصان يتحدثان عن الشيء نفسه أصلًا؟'},
 {key:'governing_rules',mark:'◆',ord:'قلب المنهج، بين السادسة والسابعة',name:'القاعدتان الحاكمتان',tag:'مستفادتان من '+BOOK,core:true},
 {key:'step7_hypotheses',mark:'7',ord:'الخطوة السابعة من إحدى عشرة',name:'توليد الفرضيات',tag:'فرضيات متعددة لمنشأ الشبهة، بلا قفز إلى أول تفسير'},
 {key:'step8_tests',mark:'8',ord:'الخطوة الثامنة من إحدى عشرة',name:'اختبار الفرضيات',tag:'لكل فرضية دليل… وإلا استُبعدت'},
 {key:'step9_map',mark:'9',ord:'الخطوة التاسعة من إحدى عشرة',name:'بناء خريطة الاستدلال',tag:'من الشبهة إلى النتيجة، خطوة خطوة'},
 {key:'review',mark:'10',ord:'الخطوة العاشرة من إحدى عشرة',name:'المراجع الناقد',tag:'طبقة ثانية تعترض قبل الإخراج'},
 {key:'step11_answer',mark:'11',ord:'الخطوة الحادية عشرة من إحدى عشرة',name:'صياغة الجواب',tag:'جواب موثّق… لا فتوى'}];
const stepAt=key=>STEPS.findIndex(s=>s.key===key);
const methodViews=new WeakMap();
const plain=v=>String(v??'').replace(/\s*\(?\b(?:RUL|SHB|FAM)-[0-9a-z]+\b\)?/gi,'').replace(/\s{2,}/g,' ').trim(); // never show internal record codes
const txt=v=>esc(ar(plain(v)));
const none='<span class="none">—</span>';
const listText=list=>(list||[]).filter(x=>String(x).trim()).map(txt).join('، ')||none;
const ICON_LOOP='<svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true"><g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8"><path d="M3 12a9 9 0 1 0 9-9a9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></g></svg>';
const ICON_SHIELD='<svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12l2 2l4-4"/></g></svg>';
const ICON_LINK='<svg width="13" height="13" viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 3h6v6m-11 5L21 3m-3 10v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>';
const rulesWord=n=>arCount(n,['قاعدة واحدة','قاعدتين','قواعد','قاعدةً','قاعدة']);

function newMethod(input){return {started:Date.now(),input,steps:{},status:{},checks:{},rounds:[],review:null,current:0,seen:0,follow:true,phase:'gather',gathered:null,result:null,received:0};}
function methodFromResult(r){
 const st=newMethod(r.input_ar);
 methodDone(st,r);st.follow=false;st.seen=STEPS.length-1;
 return st;
}
// One event from the live analysis changes the state; the view redraws what changed.
function methodEvent(st,ev){
 st.received++;
 if(ev.type==='gathered')st.gathered=ev;
 if(ev.type==='library')st.library=ev.excerpts||[];
 if(ev.type==='searching')st.searching=true;
 if(ev.type==='stage'){
  st.phase=ev.stage;
  if(ev.stage==='analyze'&&!st.status.step1_framing)st.status.step1_framing='active';
  if(ev.stage==='critic')st.status.review='active';
  if(ev.stage==='revise'||ev.stage==='retry'){for(const s of STEPS)if(s.key!=='review')st.status[s.key]='wait';st.steps={};st.checks={};st.searching=false;}
  if(ev.stage==='retry')st.status.step1_framing='active';
 }
 if((ev.type==='active'||ev.type==='step')&&st.phase==='retry')st.phase='analyze';
 if(ev.type==='active'&&st.status[ev.key]!=='done')st.status[ev.key]='active';
 if(ev.type==='step'){st.steps[ev.key]=ev.data;st.status[ev.key]=ev.key==='step11_answer'?'draft':'done';if(st.follow){st.current=stepAt(ev.key);st.seen=Math.max(st.seen,st.current);}}
 if(ev.type==='verified')st.checks[ev.key]=ev.checks;
 if(ev.type==='critic'){st.rounds.push(ev.data);st.status.review=ev.data.holds?'done':'fail';if(ev.data.holds)st.status.step11_answer='done';if(st.follow){st.current=stepAt('review');st.seen=Math.max(st.seen,st.current);}}
}
function methodDone(st,r){
 st.result=r;st.phase='done';st.library=r.library?.excerpts||st.library||[];st.web=r.web_search||null;
 const m=r.method;if(!m)return;
 st.steps={...m.steps};st.review=m.review;st.rounds=m.review?.rounds||[];st.checks={};
 for(const s of STEPS)st.status[s.key]='done';
 if(!m.review||m.review.available===false)st.status.review='skip';
 else if(!m.review.holds)st.status.review='fail';
 if(st.follow){st.current=stepAt('step11_answer');st.seen=st.current;}
}

function methodHead(st){
 const r=st.result;
 if(r){
  const a=r.analysis,answer=st.steps.step11_answer||{};
  const consulted=(r.retrieved_rules||[]).length,cited=(a.methodology_rule_ids||[]).length;
  const by=consulted?`اطّلع التحليل على ${rulesWord(consulted)} من الكتاب${cited?`، واستند إلى ${rulesWord(cited)} منها`:''}.`:'';
  return `<div class="verdict">${r.mode==='draft'?'<span class="pill draft">مسودة</span>':''}<strong>${esc(patternName(a.primary_pattern))}</strong>${answer.confidence_label?`<span class="pill">${esc(CONF[answer.confidence_label]||answer.confidence_label)}</span>`:''}<span class="pill pending">يحتاج مراجعة مختص</span></div>${by?`<p class="analysis-by">${by}</p>`:''}`;
 }
 const done=STEPS.filter(x=>['done','draft','fail'].includes(st.status[x.key])).length;
 const active=STEPS.find(x=>st.status[x.key]==='active');
 const where={retry:'تعثّر الاتصال بالنموذج لحظة، فأُعيد التحليل تلقائيًا',gather:'يجمع قواعد الكتاب ذات الصلة بالشبهة',library:'يبحث في المكتبة الشاملة: متون الحديث وشروحها ومعاجم اللغة',critic:'المراجع الناقد يفحص الجواب قبل إخراجه',revise:'لم يصمد الجواب، فعاد إلى التحليل ليصحّحه'}[st.phase]||(st.searching&&!STEPS.some(x=>st.status[x.key]==='done')?'يبحث في المصادر الموثوقة على الإنترنت':active?active.name:'يقرأ الشبهة');
 const seen=[st.gathered?.rules?`اطّلع على ${rulesWord(st.gathered.rules)} من الكتاب`:'',st.library?.length?`وعلى ${arCount(st.library.length,['نص واحد','نصين','نصوص','نصًا','نص'])} من المكتبة الشاملة`:''].filter(Boolean).join(' ');
 return `<div class="progress" role="group" aria-label="سير التحليل"><div class="progress-top"><small>يجري التحليل، الخطوة ${active?STEPS.indexOf(active)+1:Math.min(done+1,STEPS.length)} من ${STEPS.length}<span class="elapsed">، منذ <span data-elapsed></span></span></small><b>${esc(where)}…</b></div><p>${seen?esc(seen)+'. ':''}يكتمل التحليل عادة خلال دقيقة تقريبًا، وتظهر كل خطوة حين تُكتب.${st.follow?'':' <button type="button" class="quiet" data-mfollow>تابع التحليل مباشرة</button>'}</p></div>`;
}
const elapsedText=st=>{const sec=Math.max(0,Math.round((Date.now()-(st.started||Date.now()))/1000));return sec<60?arCount(sec,['ثانية واحدة','ثانيتان','ثوانٍ','ثانيةً','ثانية']):`${Math.floor(sec/60)}:${String(sec%60).padStart(2,'0')} دقيقة`;};
const RAIL_STATE={done:'اكتملت',active:'جارية الآن',draft:'صيغت وتنتظر المراجعة',fail:'لم يصمد الجواب',skip:'لم تُجرَ',wait:'لم تبدأ بعد'};
const written=(st,i)=>{const s=STEPS[i];if(!s)return false;if(s.key==='review')return st.rounds.length>0||['done','fail','skip'].includes(st.status.review);return st.steps[s.key]!==undefined;};
function trailHtml(st){
 return STEPS.map((s,i)=>{const status=st.status[s.key]||'wait',open=written(st,i)&&i!==st.current;
  return `<button type="button" class="tstep ${status}${s.core?' core':''}${i===st.current?' current':''}" data-mstep="${i}"${open?'':' disabled'} aria-current="${i===st.current?'step':'false'}" aria-label="${s.name}، ${RAIL_STATE[status]}"><i aria-hidden="true"></i><span>${s.name}</span></button>`;}).join('');
}
function panelHtml(st){
 const i=st.current,s=STEPS[i],status=st.status[s.key]||'wait',d=st.steps[s.key];
 if(s.key==='step11_answer'&&d!==undefined)return answerHtml(d,st);
 const body=s.key==='review'?reviewHtml(st):d!==undefined?STEP_VIEWS[s.key](d,st):waitingHtml(status);
 const prev=STEPS[i-1],next=STEPS[i+1],ready=written(st,i+1),last=next?.key==='step11_answer';
 const forward=!next?'<span></span>':ready?`<button type="button" class="primary" data-mnav="1">${last?'اعرض الجواب':`التالي: ${next.name}`}</button>`:`<button type="button" disabled class="waiting-next"><span class="pulse" aria-hidden="true"></span>تُكتب الخطوة التالية…</button>`;
 return `<article class="panel${s.core?' core':''}" aria-label="${s.name}"><header class="panel-head"><small class="panel-ord">${s.ord}</small><h3>${s.name}</h3><p>${esc(s.tag)}</p></header><div class="panel-body">${body}</div><footer class="panel-nav">${prev?`<button type="button" class="quiet" data-mnav="-1">السابق</button>`:'<span></span>'}${forward}</footer></article>`;
}
// The answer is where the steps arrive: its own page, read as a whole, not one more step
function answerHtml(d,st){
 const lastRound=st.rounds[st.rounds.length-1],review=st.review||(lastRound?{available:true,holds:lastRound.holds}:null);
 const reviewed=st.status.step11_answer==='draft'?'<span class="b-wait">بانتظار المراجع الناقد</span>':review?.available===false?'':review?.holds?`<span class="b-ok">${ICON_SHIELD} تمت مراجعة الاستدلال</span>`:review?'<span class="b-warn">بقيت ملاحظات على الاستدلال</span>':'';
 const conf=Math.round(Math.min(1,Math.max(0,d.confidence||0))*100);
 return `<article class="panel answer" aria-label="الجواب"><header class="answer-head"><small>${STEPS[STEPS.length-1].ord}: صياغة الجواب</small><h3>الجواب</h3>${d.summary?`<p class="answer-summary">${txt(d.summary)}</p>`:''}</header>
 ${d.origin?`<section class="answer-origin"><h4>منشأ الإشكال</h4><p>${txt(d.origin)}</p></section>`:''}
 ${(d.dismantling||[]).length?`<section><h4>تفكيك الشبهة</h4><ol class="answer-steps">${d.dismantling.map(x=>`<li><p>${txt(x.step)}</p>${x.evidence?`<small>الدليل: ${txt(x.evidence)}</small>`:''}</li>`).join('')}</ol></section>`:''}
 <div class="answer-grid"><section><h4>الأدلة والمصادر</h4>${(d.sources||[]).filter(x=>String(x).trim()).length?`<ul class="answer-sources">${d.sources.filter(x=>String(x).trim()).map(x=>`<li>${txt(x)}</li>`).join('')}</ul>`:none}</section>
 <section><h4>درجة الثقة</h4><div class="m-conf"><span class="conf-track"><i data-conf="${conf}"></i></span><span>${esc(CONF[d.confidence_label]||d.confidence_label||'')}</span></div></section></div>
 ${d.disagreement?.trim()?`<section><h4>الخلاف في المسألة</h4><p>${txt(d.disagreement)}</p></section>`:''}
 ${d.revealing_question?.trim()?`<blockquote class="answer-question"><small>سؤال يكشف الإشكال</small>${txt(d.revealing_question)}</blockquote>`:''}
 ${st.web?.sources?.length?`<section><h4>مصادر البحث الموسّع</h4><ul class="m-web">${st.web.sources.map(x=>`<li><a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">${esc(x.title||x.url)} ${ICON_LINK}</a></li>`).join('')}</ul></section>`:''}
 <div class="m-badges"><span class="b-gold">عند الخلاف: يُصرَّح به</span><span>لا يُصدر فتوى، ويُحيل إلى المختص</span>${reviewed}</div>
 <footer class="panel-nav"><button type="button" class="quiet" data-mnav="-1">السابق: المراجع الناقد</button><button type="button" data-mstart>تتبّع التحليل من الخطوة الأولى</button></footer></article>`;
}
// the parts of a step rise in one after another: the rows of a list or grid, or the block itself
function stagger(body){
 let k=0;
 for(const part of body.children){
  const kids=part.children.length>1&&!/^(P|BLOCKQUOTE|H\d)$/.test(part.tagName)?[...part.children]:[part];
  for(const x of kids){x.classList.add('rise');x.style.setProperty('--i',Math.min(k++,12));}
 }
}
const waitingHtml=status=>status==='active'?'<div class="writing" role="status"><p><span class="pulse" aria-hidden="true"></span>تُكتب هذه الخطوة الآن، وتظهر هنا حين تكتمل.</p><i></i><i></i><i></i><i></i></div>':'<div class="panel-wait"><p>لم يصل التحليل إلى هذه الخطوة بعد، وستظهر هنا حين يكتبها.</p></div>';

// Texts and their checks against the Mushaf and the books of hadith
const KIND={'آية':'نص الآية','حديث':'الحديث','أثر':'الأثر','قول عالم':'قول عالم'};
const BADGE={verified:'✓ تحقق',excluded:'✗ مستبعد',mismatch:'لم يطابق مصدره',unchecked:'يحتاج تحققًا',unavailable:'تعذّر التحقق الآن',checking:'جارٍ التحقق'};
const libraryHtml=(items,title)=>items&&items.length?`<h4 class="m-sub">${title}</h4><ul class="m-library">${items.map(e=>`<li><span class="m-kind">${esc(e.label)}</span><blockquote>${esc(ar(e.text))}</blockquote><p><b>${esc(e.book)}</b>${e.vol?`، ج${esc(e.vol)}`:''}${e.page?` ص${esc(e.page)}`:''}${e.url?`<a href="${esc(e.url)}" target="_blank" rel="noopener noreferrer">افتحه في الشاملة ${ICON_LINK}</a>`:''}</p></li>`).join('')}</ul>`:'';
const withChecks=(texts,checks)=>(texts||[]).map((t,i)=>({...t,check:t.check||checks?.[i]}));
function textRow(t){
 const c=t.check||{},state=t.status==='غير ثابت'?'excluded':c.state||'checking';
 const claim=[t.source_ar?.trim()?`التخريج: ${txt(t.source_ar)}`:'',t.grade_ar?.trim()?`الدرجة: ${txt(t.grade_ar)}`:''].filter(Boolean).join('، ');
 let found='';
 if(state==='verified'){
  const grades=(c.grades||[]).map(g=>g.by?`${esc(g.by)}: ${esc(g.grade)}`:esc(g.grade)).join('، ');
  found=`<div class="m-found"><span>${esc(c.label)}: ${esc(c.reference)}${c.corrected?' (صُحّح الموضع)':''}</span>${grades?`<span>${grades}</span>`:''}${c.url?`<a href="${esc(c.url)}" target="_blank" rel="noopener noreferrer">اعرضه في مصدره ${ICON_LINK}</a>`:''}</div>${c.mushaf_text?`<p class="m-mushaf">﴿${esc(c.mushaf_text)}﴾</p>`:''}`;
 }else if(state==='excluded')found='<p class="m-check-note">نص لا يثبت، فلا يُبنى عليه الجواب.</p>';
 else if(state!=='checking'&&c.detail)found=`<p class="m-check-note">${esc(c.detail)}</p>`;
 return `<li class="m-text ${state}"><div class="m-text-head"><span class="m-kind">${KIND[t.kind]||esc(t.kind)}</span><span class="m-badge ${state}">${BADGE[state]}</span></div><p class="m-text-quote">${txt(t.quote)}</p>${claim?`<p class="m-claim">${claim}</p>`:''}${found}</li>`;
}
const ENTITIES=[['verses','الآيات'],['hadiths','الأحاديث'],['key_words','الألفاظ المحورية'],['numbers','الأرقام'],['persons','الأشخاص'],['events','الأحداث'],['rulings','الأحكام'],['terms','المصطلحات'],['claims','ادعاءات تاريخية أو علمية']];
const DIMENSIONS=['معنى اللفظ في لغة العرب','استعماله زمن النص','السياق','الحقيقة والمجاز','العموم والخصوص','الإطلاق والتقييد','دلالات الأعداد','التكثير والمبالغة','الاشتراك اللفظي','الكناية','الحذف','أساليب الخطاب'];
const CHECKS6=['جمع بين مختلفين','تفريق بين متماثلين','عام وخاص','مطلق ومقيد','حصر أم تكثير','سياق مختلف','واقعة مختلفة','صحة متساوية'];
const TONE={'نعم':'yes','لا':'no','محتمل':'maybe','مدعوم بالدليل':'yes','مرفوض':'no'};
const MAP=[['objection','الشبهة'],['hidden_assumption','الافتراض الخفي','gold'],['fault','موضع الخلل','gold'],['evidence','الدليل'],['rule','القاعدة'],['resolution','إزالة التعارض'],['conclusion','النتيجة','end']];
const CRITIC=[['misunderstood','هل أسأنا فهم الشبهة؟'],['evidence_proves','هل الدليل يثبت النتيجة فعلًا؟'],['contrary_text','هل يوجد نص يعارض الجواب؟'],['unsourced_attribution','هل نُسب قولٌ لعالم دون مصدر؟'],['possibility_as_certainty','هل جُعل الاحتمال يقينًا؟'],['stronger_explanation','هل يوجد تفسير أقوى؟']];
const CONF={'قطعي':'قطعي','راجح':'راجح','توجيه معتبر غير قطعي':'توجيه معتبر، غير قطعي','محتمل يحتاج نظرًا':'محتمل يحتاج نظرًا','ضعيف':'ضعيف'};
const findings=pairs=>pairs.length?`<dl class="m-findings">${pairs.map(([k,v])=>`<div><dt>${esc(k)}</dt><dd>${txt(v)}</dd></div>`).join('')}</dl>`:'';
const STEP_VIEWS={
 step1_framing:(d,st)=>`${st.input?`<blockquote class="m-asked">${esc(ar(st.input))}</blockquote>`:''}<dl class="m-rows">
  <div><dt>الدعوى</dt><dd>${d.claim?txt(d.claim):none}</dd></div>
  <div><dt>الأدلة</dt><dd>${(d.evidence||[]).length?`<span class="m-quotes">${d.evidence.map(x=>`<span class="m-q">${txt(x)}</span>`).join('')}</span>`:none}</dd></div>
  <div><dt>النتيجة المطلوبة</dt><dd>${d.conclusion?txt(d.conclusion):none}</dd></div>
  <div><dt>المقدّمات الصريحة</dt><dd>${listText(d.premises)}</dd></div>
  <div class="m-hidden"><dt>الافتراض الخفي</dt><dd>${d.hidden_assumption?txt(d.hidden_assumption):none}</dd></div></dl>`,
 step2_entities:d=>`<div class="m-tiles">${ENTITIES.map(([k,label])=>{const v=(d[k]||[]).filter(x=>String(x).trim());return `<div class="m-tile${v.length?'':' empty'}"><b>${label}</b><span>${v.length?v.map(txt).join('، '):'—'}</span></div>`;}).join('')}</div>`,
 step3_sources:(d,st)=>{const texts=withChecks(d.texts,st.checks.step3_sources);
  return `${texts.length?`<ul class="m-texts">${texts.map(textRow).join('')}</ul>`:'<p class="m-empty">لا تقوم الشبهة على آية ولا حديث.</p>'}${d.variants?.trim()?`<div class="m-note"><b>اختلاف الروايات</b><p>${txt(d.variants)}</p></div>`:''}<p class="m-foot">كل معلومة مربوطة بمصدرها: الآيات تُطابَق بنص المصحف، والأحاديث بكتبها وأرقامها.</p>`;},
 step4_related:(d,st)=>{const other=withChecks(d.other_texts,st.checks.step4_related);
  const node=(cls,label,list)=>{const v=(list||[]).filter(x=>String(x).trim());return `<div class="hub-node ${cls}${v.length?'':' empty'}"><b>${label}</b>${v.length?`<ul>${v.slice(0,3).map(x=>`<li>${txt(x)}</li>`).join('')}</ul>`:'<span>—</span>'}</div>`;};
  const rules=st.result?(st.result.retrieved_rules||[]).length:st.gathered?.rules||0;
  return `<div class="m-hub">${node('n-top','النصوص الأخرى في الباب',other.map(t=>t.quote))}${node('n-tr','الروايات المختلفة',d.narrations)}${node('n-tl','السياق التاريخي',d.context)}<div class="hub-center"><b>المسألة</b><span>${d.issue?txt(d.issue):'—'}</span></div>${node('n-br','شروح العلماء',d.scholars)}${node('n-bl','القواعد الأصولية',d.usul)}${node('n-bottom','كلام أهل اللغة',d.language)}</div>${rules?`<p class="m-foot">ومن الكتاب: اطّلع التحليل على ${rulesWord(rules)} ذات صلة بالمسألة.</p>`:''}${other.length?`<h4 class="m-sub">التحقق من النصوص الأخرى</h4><ul class="m-texts">${other.map(textRow).join('')}</ul>`:''}${libraryHtml((st.library||[]).filter(e=>e.kind!=='lugha'),'من المكتبة الشاملة: المتون والشروح')}`;},
 step5_language:(d,st)=>{const found=new Map((d.findings||[]).map(f=>[f.dimension,f.finding]));
  return `<div class="m-cells four">${DIMENSIONS.map(x=>`<span class="m-cell${found.has(x)?' on':''}">${x}</span>`).join('')}</div>${findings([...found])||'<p class="m-empty">لم يتبيّن جانب لغوي مؤثر في هذه الشبهة.</p>'}${libraryHtml((st.library||[]).filter(e=>e.kind==='lugha'),'من معاجم اللغة في المكتبة الشاملة')}`;},
 step6_comparison:d=>{const notes=new Map((d.checks||[]).map(c=>[c.check,c.finding]));
  const q=(label,a)=>`<div class="m-qa"><span>${label}</span><em class="ans ${TONE[a?.answer]||'maybe'}">${esc(a?.answer||'—')}</em>${a?.why?`<p>${txt(a.why)}</p>`:''}</div>`;
  return `<div class="m-compare"><div class="m-side"><small>النص (أ)</small><b>${d.side_a?txt(d.side_a):'—'}</b></div><div class="m-qs">${q('الشيء نفسه؟',d.same_thing)}${q('الجهة نفسها؟',d.same_aspect)}${q('الدلالة نفسها؟',d.same_meaning)}</div><div class="m-side"><small>النص (ب)</small><b>${d.side_b?txt(d.side_b):'—'}</b></div></div><div class="m-cells">${CHECKS6.map(c=>`<span class="m-cell${notes.has(c)?' on':''}">${c}؟</span>`).join('')}</div>${findings([...notes])}${d.conclusion?`<p class="m-conclusion">${txt(d.conclusion)}</p>`:''}`;},
 governing_rules:(d,st)=>{const p=d.primary_pattern,gathers=p==='جمع بين مختلفين'||p==='mixed_pattern',splits=p==='تفريق بين متماثلين'||p==='mixed_pattern';
  const card=(hit,title,sub,art)=>`<div class="rule-card ${hit?'hit':'miss'}"><h4>${title}</h4><p>${sub}</p><div class="rule-art" aria-hidden="true">${art}</div><span class="rule-flag">${hit?'✓ هنا وقع الخلل':'✗ غير منطبق'}</span></div>`;
  const c=st.steps.step6_comparison,decided=gathers||splits;
  const rule=st.result?.analysis?.methodology_rule_ar;
  const cites=(st.result?.source_evidence||[]).map(x=>`<button type="button" class="quiet" data-book="${esc(x.source?.source_id||'')}" data-bookpage="${x.source?.page_number||1}" data-booktitle="${esc(x.source?.source_name||'')}">افتح الكتاب، صفحة ${x.source?.page_number??''}</button>`).join('');
  return `<div class="m-rules">${card(gathers,'الجمع بين المختلفين','معاملة المختلفين معاملةً واحدة','<i class="sq"></i><b>=</b><i class="ci"></i>')}${card(splits,'التفريق بين المتماثلين','مغايرة المتماثلين في الحكم','<i class="ci"></i><b class="ne">≠</b><i class="ci"></i>')}</div>${decided&&c?.side_a&&c?.side_b?`<p class="rule-pair">${txt(c.side_a)} ↔ ${txt(c.side_b)}</p>`:''}<div class="m-fault"><h4>${decided?`موضع الخلل: ${d.fault?txt(d.fault):esc(patternName(p))}`:esc(patternName(p))}</h4>${d.explanation?`<p>${txt(d.explanation)}</p>`:''}${(d.sub_patterns||[]).length?`<p class="m-subp">${d.sub_patterns.map(x=>`<span class="pill">${esc(subName(x))}</span>`).join(' ')}</p>`:''}</div>${rule?`<div class="m-bookrule"><b>القاعدة من الكتاب</b><p>${txt(rule)}</p>${cites}</div>`:''}`;},
 step7_hypotheses:d=>`<div class="m-hyps">${(d||[]).map(h=>`<div class="hyp"><small>${esc(h.id)}</small><b>${txt(h.title)}</b>${h.basis?`<p>${txt(h.basis)}</p>`:''}</div>`).join('')}</div>`,
 step8_tests:(d,st)=>{const titles=new Map((st.steps.step7_hypotheses||[]).map(h=>[h.id,h.title]));
  return `<div class="m-hyps">${(d||[]).map(t=>{const tone=TONE[t.verdict]||'maybe';return `<div class="hyp ${tone}"><small>${esc(t.id)}</small><b>${txt(titles.get(t.id)||t.id)}</b><span class="verdict-pill ${tone}">${tone==='yes'?'✓ ':tone==='no'?'✗ ':'◆ '}${esc(t.verdict)}</span>${t.evidence?`<p>${txt(t.evidence)}</p>`:''}</div>`;}).join('')}</div><p class="m-motto">لا تفسير جميل بلا مصدر.</p>`;},
 step9_map:d=>`<ol class="m-map">${MAP.map(([k,label,tone],i)=>`<li class="map-node n${i+1}${tone?' '+tone:''}"><b>${label}</b><span>${d[k]?txt(d[k]):'—'}</span></li>`).join('')}</ol>`,
 step11_answer:(d,st)=>{const last=st.rounds[st.rounds.length-1],review=st.review||(last?{available:true,holds:last.holds}:null);
  const reviewed=st.status.step11_answer==='draft'?'<span class="b-wait">بانتظار المراجع الناقد</span>':review?.available===false?'':review?.holds?`<span class="b-ok">${ICON_SHIELD} تمت مراجعة الاستدلال</span>`:review?'<span class="b-warn">بقيت ملاحظات على الاستدلال</span>':'';
  return `<dl class="m-answer">
  <div><dt>خلاصة الشبهة</dt><dd>${d.summary?txt(d.summary):none}</dd></div>
  <div><dt>منشأ الإشكال</dt><dd>${d.origin?txt(d.origin):none}</dd></div>
  <div><dt>التفكيك</dt><dd>${(d.dismantling||[]).length?`<ol class="m-steps">${d.dismantling.map(x=>`<li><span>${txt(x.step)}</span>${x.evidence?`<small>الدليل: ${txt(x.evidence)}</small>`:''}</li>`).join('')}</ol>`:none}</dd></div>
  <div><dt>الأدلة والمصادر</dt><dd>${listText(d.sources)}</dd></div>
  ${d.disagreement?.trim()?`<div><dt>الخلاف في المسألة</dt><dd>${txt(d.disagreement)}</dd></div>`:''}
  ${d.revealing_question?.trim()?`<div><dt>سؤال يكشف الإشكال</dt><dd>${txt(d.revealing_question)}</dd></div>`:''}
  <div><dt>درجة الثقة</dt><dd class="m-conf"><span class="conf-track"><i data-conf="${Math.round(Math.min(1,Math.max(0,d.confidence||0))*100)}"></i></span><span>${esc(CONF[d.confidence_label]||d.confidence_label||'')}</span></dd></div>
  ${st.web?.sources?.length?`<div><dt>مصادر البحث الموسّع</dt><dd><ul class="m-web">${st.web.sources.map(x=>`<li><a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">${esc(x.title||x.url)} ${ICON_LINK}</a></li>`).join('')}</ul></dd></div>`:''}
  </dl><div class="m-badges"><span class="b-gold">عند الخلاف: يُصرَّح به</span><span>لا يُصدر فتوى، ويُحيل إلى المختص</span>${reviewed}</div>`;},
};
function reviewHtml(st){
 const status=st.status.review||'wait',last=st.rounds[st.rounds.length-1];
 if(st.review&&st.review.available===false)return '<div class="panel-wait"><p>تعذّر إجراء المراجعة الناقدة هذه المرة، فراجع الجواب بعناية قبل الاعتماد عليه.</p></div>';
 if(!last)return `<div class="m-critic pending">${CRITIC.map(([,q])=>`<div class="cq"><span class="mark" aria-hidden="true"></span><b>${q}</b></div>`).join('')}</div>${status==='active'?'<div class="panel-wait live"><span class="pulse" aria-hidden="true"></span><p>يفحص المراجع الناقد الجواب الآن…</p></div>':'<div class="panel-wait"><p>تبدأ المراجعة بعد اكتمال صياغة الجواب، فإن لم يصمد عاد إلى التحليل.</p></div>'}`;
 const first=st.rounds.length>1?st.rounds[0]:null,returning=!last.holds&&st.phase==='revise';
 return `<div class="m-critic">${CRITIC.map(([k,q])=>{const c=last[k]||{};return `<div class="cq ${c.ok?'ok':'bad'}"><span class="mark" aria-hidden="true">${c.ok?'✓':'✗'}</span><b>${q}</b>${c.note?.trim()?`<p>${txt(c.note)}</p>`:''}</div>`;}).join('')}</div>${first?`<div class="m-loop">${ICON_LOOP}<div><b>لم يصمد الجواب في المراجعة الأولى، فعاد إلى التحليل</b>${first.revision?`<p>${txt(first.revision)}</p>`:''}</div></div>`:''}${status==='active'?'<div class="panel-wait live"><span class="pulse" aria-hidden="true"></span><p>يُعاد فحص الجواب بعد تصحيحه…</p></div>':`<p class="m-verdict ${last.holds?'ok':returning?'loop':'bad'}">${last.holds?`${ICON_SHIELD} صمد الجواب أمام المراجعة`:returning?`${ICON_LOOP} لم يصمد الجواب؟ يعود إلى التحليل`:`بقيت ملاحظات على الجواب، فخُفّضت درجة الثقة.${last.revision?' '+txt(last.revision):''}`}</p>`}`;
}

function mountMethod(root,st){methodViews.set(root,st);
 if(!st.result){const clock=setInterval(()=>{const el=root.querySelector('[data-elapsed]');if(st.result||!root.isConnected){clearInterval(clock);return;}if(el)el.textContent=elapsedText(st);},1000);}root.innerHTML=`<div class="method-head" data-mhead aria-live="polite"></div><div class="method-body"><div class="trail" role="group" aria-label="خطوات التحليل" data-mtrail></div><div class="stage" data-mstage></div></div>`;updateMethod(root);}
function updateMethod(root,{animate=0}={}){
 const st=methodViews.get(root);if(!st)return;
 // the status line is read aloud when it changes, so it is rewritten only then
 const head=root.querySelector('[data-mhead]'),headHtml=methodHead(st);if(head.dataset.html!==headHtml){head.innerHTML=headHtml;head.dataset.html=headHtml;}
 const clock=head.querySelector('[data-elapsed]');if(clock)clock.textContent=elapsedText(st);
 // while the analysis is being written the step glows; the path keeps the current step in sight on a narrow screen
 root.classList.toggle('live',!st.result);
 const trail=root.querySelector('[data-mtrail]');syncTrail(trail,st);
 const here=trail.querySelector('.current');
 if(here&&trail.scrollWidth>trail.clientWidth){const tr=trail.getBoundingClientRect(),hr=here.getBoundingClientRect();trail.scrollLeft+=hr.left-tr.left-(tr.width-hr.width)/2;}
 const s=STEPS[st.current],stage=root.querySelector('[data-mstage]');
 const sig=JSON.stringify([st.current,st.status[s.key]||'',st.steps[s.key]??null,st.checks[s.key]??null,written(st,st.current+1),s.key==='review'||s.key==='step11_answer'?[st.rounds,st.phase,st.review,st.status.step11_answer]:0,s.key==='governing_rules'?Boolean(st.result):0]);
 if(stage.dataset.sig===sig)return;
 stage.dataset.sig=sig;
 const old=stage.querySelector('.panel:not(.leaving)');
 stage.querySelectorAll('.panel.leaving').forEach(p=>p.remove());
 const box=document.createElement('div');box.innerHTML=panelHtml(st);const panel=box.firstElementChild;
 panel.dataset.step=st.current;
 panel.querySelectorAll('[data-conf]').forEach(i=>{i.style.width=i.dataset.conf+'%';});
 // the same step with new details (a text checked, the next step written): only the parts that changed are swapped,
 // so nothing on the page flickers or replays
 if(!animate&&old&&old.dataset.step===panel.dataset.step&&old.children.length===panel.children.length&&baseClass(old)===baseClass(panel)){
  [...panel.children].forEach((part,i)=>{const html=part.outerHTML,cur=old.children[i];if(partHtml.get(cur)!==html){partHtml.set(part,html);cur.replaceWith(part);}});
  return;
 }
 for(const part of panel.children)partHtml.set(part,part.outerHTML);
 // a new step opens out of its own step in the list and its parts rise in; the window just read fades where it is
 if(animate&&old&&!calm()){
  old.classList.remove('entering','expanding','fade-in'); // a window that came in animated must now play its way out, not in again
  old.getAnimations().forEach(a=>{if(a instanceof CSSAnimation)return;a.finish();});
  old.classList.add('leaving');old.setAttribute('inert','');old.setAttribute('aria-hidden','true');
  setTimeout(()=>old.remove(),320);
  panel.classList.add('entering');
  stagger(panel.querySelector('.panel-body')||panel);
  stage.append(panel);
  // the window opens where the reader can see it: if its top has gone above the screen, the page comes to it first
  const top=stage.getBoundingClientRect().top;if(top<0)scrollTo(0,scrollY+top-16);
  if(!openFromStep(panel,trail.querySelector('.tstep.current')))panel.classList.add('fade-in'); // no step to open from: a plain fade
 }else{old?.remove();stage.append(panel);}
}
const partHtml=new WeakMap();
const baseClass=el=>[...el.classList].filter(c=>!['entering','expanding','leaving','fade-in'].includes(c)).sort().join(' ');
// The list of steps keeps its buttons; only what changed on each (state, place, availability) is updated, so the
// step being written keeps its running light and nothing in the list flashes on every update
function syncTrail(trail,st){
 const box=document.createElement('div');box.innerHTML=trailHtml(st);
 if(trail.children.length!==box.children.length){trail.replaceChildren(...box.children);return;}
 [...box.children].forEach((fresh,i)=>{const cur=trail.children[i];
  for(const name of ['class','aria-current','aria-label'])if(cur.getAttribute(name)!==fresh.getAttribute(name))cur.setAttribute(name,fresh.getAttribute(name));
  cur.disabled=fresh.disabled;});
}
// The window grows out of its step, the way a window opens from its icon: it starts small at the step's place (on the
// window's edge beside the list, or under the step when the list is above) and opens to its full size. Only scale and
// opacity change, which the graphics card draws without repainting the page, so it stays smooth.
function openFromStep(panel,step){
 if(!step||!panel.animate)return false;
 const p=panel.getBoundingClientRect(),s=step.getBoundingClientRect();if(!p.width||!p.height||!s.width)return false;
 const clamp=(v,lo,hi)=>Math.min(hi,Math.max(lo,v)),mid=clamp(s.top+s.height/2-p.top,0,p.height);
 const [x,y]=s.left>=p.right-2?[p.width,mid]:s.right<=p.left+2?[0,mid]:[clamp(s.left+s.width/2-p.left,0,p.width),0];
 panel.classList.add('expanding');panel.style.transformOrigin=`${Math.round(x)}px ${Math.round(y)}px`;
 panel.animate([{transform:'scale(.06)',opacity:0},{transform:'scale(1)',opacity:1}],{duration:540,easing:'cubic-bezier(.2,.75,.25,1)'})
  .finished.then(()=>{panel.classList.remove('expanding');panel.style.transformOrigin='';},()=>{});
 return true;
}
function goStep(root,index){
 const st=methodViews.get(root);if(!st)return;
 const next=Math.min(STEPS.length-1,Math.max(0,index));if(next===st.current)return;
 // any step already written can be opened; one still being written cannot
 if(!written(st,next))return;
 const dir=Math.sign(next-st.current);st.current=next;st.seen=Math.max(st.seen,next);st.follow=false;updateMethod(root,{animate:dir});
}
// Left and right arrows move along the path (right-to-left: left is the next step).
document.addEventListener('keydown',e=>{
 if(e.key!=='ArrowLeft'&&e.key!=='ArrowRight')return;
 const root=e.target.closest?.('[data-method]');if(!root||!e.target.closest('.trail, .panel-nav'))return;
 e.preventDefault();const st=methodViews.get(root);goStep(root,st.current+(e.key==='ArrowLeft'?1:-1));
 root.querySelector('.panel:not(.leaving) .panel-nav [data-mnav]')?.focus({preventScroll:true});
});
const abstentions={
 no_approved_methodology:['لم تُعتمد قواعد تناسب هذه الشبهة بعد','يستند التحليل إلى قواعد الكتاب المعتمدة وحدها، ولم يُعتمد منها بعد ما ينطبق على هذه الشبهة. يمكنك إعادة التحليل بكل قواعد الكتاب، وتُعلَّم النتيجة «مسودة».'],
 model_or_grounding_validation_failed:['لم يُقبل الاقتراح','اقترح النموذج تشخيصًا لا يستند إلى قاعدة من القواعد التي اطّلع عليها، فاستُبعد حفاظًا على الدقة. جرّب صياغة الشبهة بعبارة أوضح.'],
 model_not_configured:['خدمة التحليل غير مفعّلة','لم تُضبط خدمة الذكاء الاصطناعي على الخادم. تواصل مع مسؤول المشروع.'],
 retrieval_unavailable:['تعذّر البحث في الكتاب الآن','لم يتمكن النظام من الوصول إلى قواعد الكتاب في هذه اللحظة. حاول بعد قليل.'],
 safety_gate:['أُوقفت النتيجة','خرجت النتيجة عن حدود التحليل المنهجي، فأوقفها النظام ولم تُعرض.']};
function diagnosisHtml(r,{retry=false}={}){
 if(r.abstention_reason){
  const [head,why]=abstentions[r.abstention_reason]||['لم تُصنَّف الشبهة','لم يتمكن النظام من تصنيف هذه الشبهة.'];
  const again=retry&&r.abstention_reason==='no_approved_methodology'&&r.mode!=='draft'?'<button type="button" class="primary" data-retry-drafts>أعد التحليل بكل قواعد الكتاب</button>':'';
  return `<div class="abstain"><img src="/static/img/emblem.webp" alt="" width="36" height="36"><div><h4>${esc(head)}</h4><p>${esc(why)}</p>${again}</div></div>${feedbackHtml(r)}`;
 }
 const a=r.analysis,draft=r.mode==='draft',item=(label,value)=>plain(value)?`<dt>${label}</dt><dd>${esc(ar(plain(value)))}</dd>`:'';
 const list=(label,values)=>values&&values.length?`<dt>${label}</dt><dd><ol>${values.map(x=>`<li>${esc(plain(x))}</li>`).join('')}</ol></dd>`:'';
 const cites=r.source_evidence.map(c=>`<li><button class="quiet" data-book="${esc(c.source?.source_id||'')}" data-bookpage="${c.source?.page_number||1}" data-booktitle="${esc(c.source?.source_name||'')}">${esc(c.source?.source_name||'')}، صفحة ${c.source?.page_number??''}</button> ${badge(c.review_status||'approved')}</li>`).join('');
 const consulted=(r.retrieved_rules||[]).length,cited=(a.methodology_rule_ids||[]).length;
 const by=consulted?`اطّلع النظام على ${rulesWord(consulted)} من الكتاب${cited?`، واستند التشخيص إلى ${rulesWord(cited)} منها`:''}.`:'';
 const note='اقتراح مستند إلى قواعد الكتاب، يحتاج مراجعة مختص.';
 const confidence=a.confidence!=null?` درجة الثقة ${num(Math.round(a.confidence*100))}%.`:'';
 return `${by?`<p class="analysis-by">${by}</p>`:''}<div class="verdict">${draft?'<span class="pill draft">مسودة</span>':''}<strong>${esc(patternName(a.primary_pattern))}</strong><span class="pill pending">يحتاج مراجعة مختص</span></div><dl class="diagnosis">${item('ما يدّعيه المعترض',a.central_claim_ar)}${list('تفاصيل الدعوى',a.subclaims_ar)}${list('طرفا المقارنة',a.compared_entities_ar.map(x=>x.entity_a+' مقابل '+x.entity_b))}${list('تفصيل التشخيص',a.sub_patterns.map(subName))}${item('سبب التشخيص',a.diagnostic_reason_ar)}${item('سؤال يكشف الإشكال',a.revealing_question_ar)}${item('القاعدة من الكتاب',a.methodology_rule_ar)}${item('طريقة المعالجة',a.treatment_ar)}${list('خطوات الرد',a.response_path_ar)}${cites?`<dt>المصادر</dt><dd><ul class="cites">${cites}</ul></dd>`:''}</dl><small class="meta">${esc(note)}${confidence}</small>${feedbackHtml(r)}`;
}
const feedbackHtml=r=>r.id?`<div class="feedback" data-fb="${esc(r.id)}"><span>هل التحليل صحيح؟</span><button type="button" data-fb-verdict="correct" class="${r.feedback?.verdict==='correct'?'chosen':''}">صحيح</button><button type="button" data-fb-verdict="wrong" class="${r.feedback?.verdict==='wrong'?'chosen':''}">فيه خطأ</button></div>`:'';
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
 if(b.dataset.chunks){const chunks=await api('/sources/'+b.dataset.chunks+'/chunks');$('#editor-content').innerHTML='<header class="modal-head"><div class="modal-title"><h3 id="editor-title">النص المستخرج من الكتاب</h3></div><button data-action="close">إغلاق</button></header><div class="chunks">'+chunks.map(c=>`<details><summary>صفحة ${num(c.page_number)}: ${esc(c.section)}</summary><pre class="excerpt">${esc(ar(c.text))}</pre></details>`).join('')+'</div>';$('#editor').showModal();}
 if(b.dataset.history&&!b.closest('details').open){const history=await api('/records/'+b.dataset.history+'/history');$('#history').innerHTML=history.map(x=>`<li><b>الإصدار ${num(x.snapshot.version)}</b> ${esc(historyActions[x.action]||x.action)}، ${esc(/^machine:/.test(x.actor)?'النظام':x.actor_name||x.actor)}، ${esc(new Date(x.at).toLocaleString('ar-u-nu-latn'))}</li>`).join('');}
 const action=b.dataset.action;
 if(action==='close')closeDialog($('#editor'));
 if(action==='close-book')closeDialog($('#book'));
 if(action==='close-auth')closeDialog($('#auth'));
 if(b.dataset.mstep!==undefined)goStep(b.closest('[data-method]'),Number(b.dataset.mstep));
 if(b.dataset.mnav)goStep(b.closest('[data-method]'),methodViews.get(b.closest('[data-method]')).current+Number(b.dataset.mnav));
 if(b.hasAttribute('data-mstart')){const root=b.closest('[data-method]');methodViews.get(root).seen=0;goStep(root,0);} // walked again from the start, one step at a time
 if(b.hasAttribute('data-mfollow')){const root=b.closest('[data-method]'),st=methodViews.get(root);st.follow=true;
  const reached=STEPS.reduce((last,s,i)=>written(st,i)?i:last,0);st.seen=Math.max(st.seen,reached);goStep(root,reached);st.follow=true;updateMethod(root);}
 if(b.hasAttribute('data-retry-drafts')){const text=b.closest('.thread')?.querySelector('.msg.me p')?.textContent||'';await showThread(null);$('#diagnose-text').value=text;document.querySelector('input[name=rules-source][value=all]').checked=true;$('#diagnose-form').requestSubmit($('#diagnose-submit'));}
 if(b.id==='history-more')await refreshHistory(true);
 if(b.dataset.diag)await openAnalysis(b.dataset.diag);
 if(b.hasAttribute('data-chat-new'))await showThread(null);
 if(b.hasAttribute('data-chat-list'))toggleList();
 if(b.dataset.example){const t=$('#diagnose-text');if(t){t.value=b.dataset.example;fit(t);t.focus();}}
 if(b.dataset.deleteOne){const gone=b.dataset.deleteOne;if(await confirmBox({title:'حذف هذا التحليل؟',message:'سيُحذف من سجلك نهائيًا مع أسئلته، ولا يمكن استرجاعه.',confirm:'حذف',danger:true})){await api('/diagnoses/'+gone,{method:'DELETE'});closeDialog($('#editor'));notify('حُذف التحليل من سجلك.');
  const row=document.querySelector(`.chat-item[data-chat="${CSS.escape(gone)}"]`);
  if(row&&!calm()&&row.animate){row.style.overflow='hidden';await settled(row.animate([{opacity:1,height:row.offsetHeight+'px'},{opacity:0,height:'0px'}],{duration:260,easing:'cubic-bezier(.4,0,.2,1)',fill:'forwards'}),320);}
  if(gone===chatActive)await showThread(null);refreshHistory().catch(()=>{});}}
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
 if(id==='ingest-form'){const form=new FormData();form.append('file',$('#pdf-file').files[0]);form.append('title',$('#pdf-title').value);form.append('author',$('#pdf-author').value);form.append('profile',$('#pdf-profile').value);notify('يجري استخراج الصفحات، وقد يستغرق ذلك عدة دقائق.');const r=await api('/ingest',{method:'POST',body:form});notify('سجلات جديدة بانتظار المراجعة: '+num(r.candidate_count));await render();}
 if(id==='diagnose-form'){
  const body={text:$('#diagnose-text').value.trim(),include_drafts:document.querySelector('input[name=rules-source]:checked')?.value==='all'};
  if(!body.text)return;
  const thread=$('#thread');chatActive=null;markActive();threadSeq++;
  await threadOut(thread);
  thread.innerHTML=conversationHtml(body.text,'');threadIn(thread);scrollTo(0,0);
  const bot=thread.querySelector('.msg.bot.analysis'),root=bot.querySelector('[data-method]'),st=newMethod(body.text);mountMethod(root,st);
  let r;
  try{
   try{r=await api('/diagnose/stream',{method:'POST',body,stream:event=>{const before=st.current;methodEvent(st,event);updateMethod(root,{animate:Math.sign(st.current-before)});}});}
   catch(err){if(err.status!==404&&err.status!==405)throw err;r=await api('/diagnose',{method:'POST',body});} // a server without the live analysis
  }catch(err){bot.innerHTML=`<div class="panel-wait"><p>${esc(err.message)}</p></div>`;refreshHistory().catch(()=>{});return;}
  const here=root.isConnected;
  if(r.method){methodDone(st,r);updateMethod(root,{animate:1});const after=bot.querySelector('[data-after]');after.innerHTML=feedbackHtml(r);
   if(!calm()&&after.animate)after.animate([{opacity:0},{opacity:1}],{duration:420,delay:380,easing:'ease-out',fill:'backwards'});} // after the answer has opened
  else bot.innerHTML=diagnosisHtml(r,{retry:true});
  if(here&&r.id){chatActive=r.id;const foot=thread.querySelector('.thread-foot');if(foot&&r.method)foot.innerHTML=askHtml(r.id);}
  await refreshHistory().catch(()=>{});markActive();}
 if(id==='ask-form'){
  const did=e.target.dataset.did,input=$('#ask-text'),question=input.value.trim();if(!did||!question)return;
  input.value='';fit(input);
  const turns=$('#turns');
  turns.insertAdjacentHTML('beforeend',`<div class="msg me"><p>${esc(question)}</p></div><div class="msg bot"><div class="md thinking" role="status"><span class="dots" aria-label="يكتب الجواب"><i></i><i></i><i></i></span></div></div>`);
  // the question and the answer's place rise in together, as a sent message does
  if(!calm())[...turns.children].slice(-2).forEach((x,i)=>x.animate?.([{opacity:0,transform:'translateY(10px)'},{opacity:1,transform:'none'}],{duration:340,delay:i*90,easing:'cubic-bezier(.2,.8,.2,1)',fill:'backwards'}));
  const out=turns.lastElementChild.querySelector('.md');out.scrollIntoView({block:'nearest',behavior:calm()?'auto':'smooth'});
  const follow=()=>{if(innerHeight+scrollY>=document.documentElement.scrollHeight-180)scrollTo(0,document.documentElement.scrollHeight);};
  let text='';
  try{
   const turn=await api(`/diagnoses/${did}/ask`,{method:'POST',body:{question},stream:ev=>{if(ev.type!=='delta')return;text+=ev.text;out.classList.remove('thinking');out.innerHTML=md(text);follow();}});
   out.classList.remove('thinking');out.innerHTML=md(turn.answer);
  }catch(err){out.classList.remove('thinking');out.innerHTML=`<p class="md-error">${esc(err.message)}</p>`;}
  out.removeAttribute('role');
 }
 if(id==='research-form'){const r=await api('/research',{method:'POST',body:{topic:$('#research-topic').value,limit:Number($('#research-limit').value)}});notify('حالات جديدة: '+num(r.record_ids.length)+'، ومصادر تعذر الوصول إليها: '+num(r.errors.length));await render();}
 if(id==='gate-form'){await api('/phase-two/enable',{method:'POST',body:{coverage_verified:$('#coverage-check').checked,notes:$('#coverage-notes').value}});notify('وُثّق اكتمال مراجعة الكتاب.');}
 if(id==='benchmark-form'){const ids=s=>$(s).value.split(/[\n,،]/).map(x=>x.trim()).filter(Boolean);await api('/benchmark',{method:'POST',body:{test_ids:ids('#test-ids'),validation_ids:ids('#validation-ids')}});notify('حُفظت مجموعة الاختبار.');await render();}
 if(id==='export-form'){const blob=await api('/export/'+$('#manifest').value,{method:'POST',blob:true});await download(blob,'manhaj-training.jsonl');await render();}
 }catch(err){notify(err.message,'error');}finally{if(button){button.disabled=false;button.classList.remove('busy');if(button.dataset.label){button.textContent=button.dataset.label;delete button.dataset.label;}}}
});
// Enter in the search box searches; Enter in a one-line review field must not trigger "approve".
document.addEventListener('change',e=>{if(e.target.closest('.attest .check')&&e.target.checked)e.target.closest('.check').classList.remove('missing');});
document.addEventListener('keydown',e=>{if(e.key!=='Enter')return;if(e.target.id==='search'){e.preventDefault();clearTimeout(searchTimer);query=e.target.value.trim();offset=0;render().catch(err=>notify(err.message));}else if(e.target.matches('#review-form input:not([type=checkbox]), #edit-title_ar'))e.preventDefault();});
// Landing: the path as a deck of windows. Each step opens an example window on top of the ones
// already seen (the seventy-autumns question, drawn with the site's own step views); the reader moves on.
const DEMO_TEXT=(quote,collection,number,source,grade,reference,grades)=>({kind:'حديث',quote,surah:0,ayah:0,collection,number,source_ar:source,grade_ar:grade,status:'ثابت',check:{state:'verified',label:'وُجد في مصدره',reference,grades}});
const DEMO={input:'كيف يقول ﷺ: «سبعين خريفًا»، وفي حديث آخر: «مائة عام»؟ أليس هذا تناقضًا؟',gathered:{rules:6},
 library:[{kind:'sharh',label:'شروح الحديث',book:'البحر المحيط الثجاج في شرح صحيح مسلم',vol:'21',page:383,text:'قوله: «سبعين خريفًا» ليس للتحديد، وإنما هو للتكثير بدليل روايته بلفظ: «مائة عام».',url:'https://shamela.ws/book/148870/12595'},
  {kind:'hadith',label:'متون الحديث',book:'صحيح سنن النسائي',vol:'2',page:480,text:'من صام يومًا في سبيل الله باعد الله منه جهنم مسيرة مائة عام.',url:'https://shamela.ws/book/1147/488'},
  {kind:'lugha',label:'معاجم اللغة',book:'لسان العرب',vol:'9',page:63,text:'ليس الخريف في الأصل باسم الفصل، وإنما هو اسم مطر القيظ، ثم سُمّي الزمن به.',url:'https://shamela.ws/book/1687/4370'}],
 status:Object.fromEntries(STEPS.map(x=>[x.key,'done'])),checks:{},review:{available:true,holds:true,revised:false},
 result:{analysis:{methodology_rule_ar:'الشريعة لا تفرّق بين المتماثلات، ولا تجمع بين المختلفات.'},source_evidence:[],retrieved_rules:[1,2,3,4,5,6]},
 rounds:[{misunderstood:{ok:true,note:'حُرّرت الدعوى كما قصدها السائل: تعارض العددين.'},evidence_proves:{ok:true,note:'كل خطوة في التفكيك مسنودة بدليلها.'},contrary_text:{ok:true,note:'لا نص يعارض حمل العدد على التكثير.'},unsourced_attribution:{ok:true,note:'الروايتان مطابقتان لمصدريهما.'},possibility_as_certainty:{ok:true,note:'وُصف الجواب بأنه توجيه معتبر غير قطعي.'},stronger_explanation:{ok:true,note:'لم يظهر تفسير أقوى.'},holds:true,revision:''}],
 steps:{
  step1_framing:{claim:'الحديثان متعارضان',evidence:['«سبعين خريفًا»','«مائة عام»'],conclusion:'في النصوص تناقض',premises:['العددان مختلفان'],hidden_assumption:'العددان يُقارنان حسابيًا'},
  step2_entities:{verses:[],hadiths:['حديثان'],key_words:['«خريف»','«في سبيل الله»'],numbers:['70','100'],persons:['الرواة والصحابة'],events:[],rulings:['فضل الصيام'],terms:['الخريف = العام'],claims:[]},
  step3_sources:{texts:[DEMO_TEXT('من صام يومًا في سبيل الله بعّد الله وجهه عن النار سبعين خريفًا','bukhari',2840,'رواه البخاري ومسلم','صحيح','صحيح البخاري (2840)',[{by:'',grade:'صحيح، أخرجه البخاري في صحيحه'}]),
   DEMO_TEXT('من صام يومًا في سبيل الله باعد الله منه جهنم مسيرة مائة عام','nasai',2254,'رواه النسائي','حسن','سنن النسائي (2254)',[{by:'الألباني',grade:'حسن'}])],variants:'رواية «سبعين خريفًا» في الصحيحين، ورواية «مائة عام» عند النسائي.'},
  step4_related:{issue:'فضل صيام يوم في سبيل الله',other_texts:[],narrations:['تعددت الروايات في العدد'],scholars:['حمل أهل العلم العدد على التكثير'],language:['الخريف يُطلق ويُراد به العام'],usul:['العدد لا مفهوم له إذا عارضه ما هو أقوى'],context:['الحث على الصيام في الجهاد']},
  step5_language:{findings:[{dimension:'دلالات الأعداد',finding:'السبعون والمائة لا يُراد بهما الحصر'},{dimension:'التكثير والمبالغة',finding:'العرب تذكر هذه الأعداد للتكثير'}]},
  step6_comparison:{side_a:'«سبعين خريفًا»',side_b:'«مائة عام»',same_thing:{answer:'نعم',why:'كلاهما في فضل صوم يوم في سبيل الله'},same_aspect:{answer:'محتمل',why:'قد يختلف بحال الصائم وإخلاصه'},same_meaning:{answer:'لا',why:'العدد للتكثير لا للحساب'},checks:[{check:'حصر أم تكثير',finding:'العددان للتكثير'},{check:'جمع بين مختلفين',finding:'قورن عدد للتكثير بعدد آخر حسابيًا'}],conclusion:'لا تعارض؛ فالعددان لا يُقصد بهما التحديد.'},
  governing_rules:{primary_pattern:'جمع بين مختلفين',sub_patterns:['اختلاف المعنى'],fault:'جمعٌ بين مختلفين',explanation:'سوّى بين عددٍ قد يُراد به التكثير وعددٍ آخر، ثم قارنهما حسابيًا.',methodology_rule_ids:[]},
  step7_hypotheses:[{id:'H1',title:'المشكلة لغوية',basis:'دلالة العدد في لغة العرب'},{id:'H2',title:'المشكلة حديثية',basis:'اختلاف الروايات'},{id:'H3',title:'تفريق بين متماثلين',basis:'هل فُرّق بين أمرين متماثلين؟'},{id:'H4',title:'جمع بين مختلفين',basis:'قورن العددان حسابيًا'},{id:'H5',title:'مقدمة غير صحيحة',basis:'هل العددان مختلفان حقًا؟'},{id:'H6',title:'إشكال يحتاج جمع العلماء',basis:'قد يُحمل على تفاوت الأجر'}],
  step8_tests:[{id:'H1',verdict:'مدعوم بالدليل',evidence:'كلام أهل اللغة في التكثير'},{id:'H2',verdict:'مرفوض',evidence:'الروايتان ثابتتان'},{id:'H3',verdict:'مرفوض',evidence:'لا تفريق في الحكم'},{id:'H4',verdict:'مدعوم بالدليل',evidence:'العدد للتكثير لا للحساب'},{id:'H5',verdict:'مرفوض',evidence:'العددان مختلفان فعلًا'},{id:'H6',verdict:'محتمل',evidence:'يُعرض مع غيره'}],
  step9_map:{objection:'تعارض «سبعين خريفًا» و«مائة عام»',hidden_assumption:'العددان يُقارنان حسابيًا',fault:'جمعٌ بين مختلفين',evidence:'دلالة العدد على التكثير',rule:'الشريعة لا تجمع بين المختلفات',resolution:'العددان للتكثير فلا تعارض',conclusion:'لا تناقض بين الحديثين'},
  step11_answer:{summary:'تعارضٌ ظاهري بين «سبعين خريفًا» و«مائة عام»',origin:'مقارنة حسابية بين عدد يُراد به التكثير وعدد آخر',dismantling:[{step:'التعارض مبني على قراءة العددين قراءة حسابية',evidence:'لفظ الحديثين'},{step:'الروايتان ثابتتان في مصادرهما',evidence:'البخاري (2840) والنسائي (2254)'},{step:'العدد في لغة العرب يُذكر للتكثير',evidence:'كلام أهل اللغة وشُرّاح الحديث'}],sources:['صحيح البخاري','صحيح مسلم','سنن النسائي','فتح الباري'],disagreement:'',revealing_question:'هل يلزم من ذكر عددين للتكثير أن يكون أحدهما خطأً؟',confidence:.7,confidence_label:'توجيه معتبر غير قطعي'}}};
// Landing: the method as a short guided tour. One window at a time in the middle, the step's name above it;
// it moves on by itself like a video (a bar fills under each step), and the reader can pause, step back or skip.
let deckAt=0,tourPlaying=true,tourSeen=false,tourInside=false;
const PLAY_ICON='<svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z"/></svg>',PAUSE_ICON='<svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><g fill="currentColor"><rect width="5" height="18" x="14" y="3" rx="1"/><rect width="5" height="18" x="5" y="3" rx="1"/></g></svg>';
function deckWindow(s,k){
 const body=s.key==='review'?reviewHtml(DEMO):STEP_VIEWS[s.key](DEMO.steps[s.key],DEMO);
 return `<article class="win" data-win="${k}" aria-label="${s.name}"><div class="win-bar"><span class="win-dots" aria-hidden="true"><i></i><i></i><i></i></span><b>${s.name}</b><span class="win-tag">مثال توضيحي</span></div><div class="win-body">${body}</div></article>`;
}
const riseParts=w=>stagger(w.querySelector('.win-body'));
function showDeck(index){
 const deck=$('#deck');if(!deck)return;
 deckAt=(index+STEPS.length)%STEPS.length;
 deck.querySelectorAll('.win').forEach(w=>{
  const rel=Number(w.dataset.win)-deckAt,d=-rel;
  // the open window on top; the two seen before it step back behind it; the rest wait below, unseen
  w.style.transform=rel===0?'none':rel<0?`translateY(${-Math.min(d,2)*15}px) scale(${1-Math.min(d,2)*.045})`:'translateY(40px) scale(.97)';
  w.style.opacity=rel===0||(rel<0&&d<=2)?'1':'0';
  w.style.zIndex=rel>0?'31':String(30-Math.min(d,30));
  w.classList.toggle('behind',rel<0);w.toggleAttribute('inert',rel!==0);w.setAttribute('aria-hidden',String(rel!==0));
  if(rel!==0){w.classList.remove('front');return;}
  const body=w.querySelector('.win-body');body.scrollTop=0;
  w.classList.remove('front');void w.offsetWidth;w.classList.add('front');
  w.classList.toggle('long',body.scrollHeight>body.clientHeight+16);
  w.querySelectorAll('[data-conf]').forEach(i=>{i.style.width=i.dataset.conf+'%';});
 });
 const s=STEPS[deckAt],head=$('#tour .tour-head');
 $('#tour-ord').textContent=s.ord;$('#tour-title').textContent=s.name;$('#tour-tag').textContent=s.tag;
 head.classList.remove('swap');void head.offsetWidth;head.classList.add('swap');
 $('#tour-count').textContent=`${deckAt+1} من ${STEPS.length}`;
 $('#tour-progress').innerHTML=STEPS.map((x,k)=>`<button type="button" class="seg${k<deckAt?' done':k===deckAt?' now':''}" data-seg="${k}" aria-label="${x.name}"><i></i></button>`).join('');
 const fill=$('#tour-progress .now i');if(fill)fill.addEventListener('animationend',()=>{if(tourPlaying)showDeck(deckAt+1);},{once:true});
}
function setTour(playing){
 tourPlaying=playing;const t=$('#tour'),b=$('[data-tour=play]');if(!t)return;
 t.classList.toggle('paused',!playing);b.innerHTML=playing?PAUSE_ICON:PLAY_ICON;b.setAttribute('aria-label',playing?'إيقاف العرض':'تشغيل العرض');
}
// the tour plays only while the reader is inside it and the page is in front
function tourWait(){$('#tour')?.classList.toggle('waiting',document.hidden||!tourInside);}
// Scrolling to the tour opens its frame to the whole screen and draws the windows closer: the reader steps inside.
// The steps play while the reader stays there; scrolling on closes the frame again and the page goes on.
function immerse(){
 const scroll=$('#way-scroll'),stage=scroll.querySelector('.way-stage');
 scroll.closest('.land-way').classList.add('immersive');
 tourWait();
 const clamp=v=>Math.min(1,Math.max(0,v)),ease=t=>t<.5?4*t*t*t:1-(-2*t+2)**3/2;
 let queued=false;
 const frame=()=>{
  queued=false;if(document.body.dataset.mode!=='landing'){document.body.classList.remove('immersed');return;}
  const r=scroll.getBoundingClientRect(),vh=innerHeight,run=r.height-vh,pin=-r.top;
  // opening: from just before the stage reaches the top to a fifth of the way through; closing: the last stretch
  const e=ease(clamp((pin+.2*vh)/(.2*vh+.18*run))),x=ease(clamp((pin-run+.25*vh)/(.25*vh)));
  stage.style.setProperty('--e',e.toFixed(4));
  stage.style.setProperty('--c',Math.max(1-e,x).toFixed(4));
  stage.style.setProperty('--s',((.86+.14*e)*(1-.1*x)).toFixed(4));
  document.body.classList.toggle('immersed',r.top<120&&r.bottom>vh*1.15);
  const inside=e>.97&&x<.05;
  if(inside!==tourInside){tourInside=inside;tourWait();if(inside&&!tourSeen){tourSeen=true;showDeck(0);}}
 };
 const queue=()=>{if(!queued){queued=true;requestAnimationFrame(frame);}};
 addEventListener('scroll',queue,{passive:true});addEventListener('resize',queue);frame();
}
function buildDeck(){
 const deck=$('#deck'),tour=$('#tour');if(!deck)return;
 deck.innerHTML=STEPS.map(deckWindow).join('');deck.querySelectorAll('.win').forEach(riseParts);
 // nothing plays by itself for readers who prefer reduced motion; for the others the scene opens as they scroll
 const still=calm();
 setTour(!still);showDeck(0);
 if(still){tourInside=true;tourWait();}else immerse();
 tour.addEventListener('click',e=>{
  const b=e.target.closest('[data-tour],[data-seg]');if(!b)return;
  if(b.dataset.seg!==undefined)showDeck(Number(b.dataset.seg));
  else if(b.dataset.tour==='play')setTour(!tourPlaying);
  else showDeck(deckAt+(b.dataset.tour==='next'?1:-1));
 });
 // pressing inside a window means the reader wants to read it: the tour stops there and the window scrolls
 deck.addEventListener('pointerdown',()=>{if(tourPlaying)setTour(false);});
 tour.addEventListener('keydown',e=>{
  if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();showDeck(deckAt+(e.key==='ArrowLeft'?1:-1));}
  if(e.key===' '&&e.target.closest('.tour-bar')){e.preventDefault();setTour(!tourPlaying);}
 });
 document.addEventListener('visibilitychange',tourWait);
}
buildDeck();
// Smooth scrolling: a turn of the wheel carries the page to where it was sent with a slight glide, not a jump.
// Boxes that scroll on their own, open dialogs, zooming (ctrl) and touch keep the browser's own scrolling.
(function smoothWheel(){
 if(calm()||matchMedia('(pointer:coarse)').matches)return;
 let pos=scrollY,target=scrollY,running=false,last=0;
 const own=el=>{for(;el&&el!==document.body;el=el.parentElement){if(el.nodeType!==1)continue;const y=getComputedStyle(el).overflowY;if((y==='auto'||y==='scroll')&&el.scrollHeight>el.clientHeight+1)return true;}return false;};
 const step=now=>{
  if(!running)return;
  const dt=last?Math.min(now-last,64):16.7;last=now;
  pos+=(target-pos)*(1-Math.pow(.89,dt/16.7));
  if(Math.abs(target-pos)<.5){pos=target;running=false;last=0;}
  scrollTo(0,pos);if(running)requestAnimationFrame(step);
 };
 addEventListener('wheel',e=>{
  if(e.ctrlKey||Math.abs(e.deltaX)>Math.abs(e.deltaY)||document.querySelector('dialog[open]')||own(e.target))return;
  e.preventDefault();
  if(!running){pos=target=scrollY;}
  const d=e.deltaMode===1?e.deltaY*40:e.deltaMode===2?e.deltaY*innerHeight:e.deltaY;
  target=Math.max(0,Math.min(document.documentElement.scrollHeight-innerHeight,target+d));
  if(!running){running=true;requestAnimationFrame(step);}
 },{passive:false});
 for(const t of ['pointerdown','keydown','hashchange'])addEventListener(t,()=>{running=false;last=0;},true);
 // keys, the scrollbar and links move the page directly; the glide starts again from there
 addEventListener('scroll',()=>{if(!running)pos=target=scrollY;},{passive:true});
})();
init();
