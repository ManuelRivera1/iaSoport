'use strict';
const $ = id => document.getElementById(id);
const form = $('document-form');
const fields = ['project','service','kind','area','name','topic','owner','purpose','dependencies','api','errors','procedures','diagram','cors','authentication','configuration'];
const labels = {purpose:'Qué hace y para qué sirve',dependencies:'Arquitectura y dependencias',api:'API y ejemplos',errors:'Errores conocidos y soluciones',procedures:'Procedimientos de soporte',diagram:'Diagrama',cors:'CORS y orígenes permitidos',authentication:'Autenticación y permisos',configuration:'Configuración y ambientes'};
const questions = {purpose:'¿Qué necesidad resuelve y qué hace este microservicio?',dependencies:'¿Qué servicios, bases de datos o integraciones utiliza?',api:'¿Qué endpoints o comandos están verificados?',procedures:'¿Qué revisas primero cuando falla y cuándo debes escalar?',owner:'¿Qué equipo es responsable de mantenerlo?'};
let currentDraft = null, step = 1, libraryMode = 'official', official = [], draftList = [], dirty = false;
let noticeTimer;
let libraryLoading=false, libraryRequest=0;
let documentEpoch=0;
const node = (tag,text,className) => {const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;};
function notify(message,error=false){clearTimeout(noticeTimer);$('notice').textContent=message;$('notice').classList.remove('hidden');$('notice').classList.toggle('error',error);noticeTimer=setTimeout(()=>$('notice').classList.add('hidden'),9000);}
async function api(url,options={}){const r=await fetch(url,{...options,headers:{'Content-Type':'application/json',...options.headers}});let data;try{data=await r.json();}catch{throw new Error('No se pudo leer la respuesta. Intenta de nuevo.');}if(!r.ok){let detail=data.detail;if(r.status===404&&detail==="Not Found")detail="El servidor está desactualizado. Cierra la ventana de Support AI y vuelve a abrir Abrir Support AI.cmd.";if(Array.isArray(detail))detail='Revisa los campos: hay información incompleta o demasiado extensa.';throw new Error(detail||'No pudimos completar la acción. Intenta de nuevo.');}return data;}
function showView(view,refresh=true){document.querySelectorAll('.view').forEach(el=>el.classList.toggle('hidden',el.id!==`view-${view}`));document.querySelectorAll('.nav-item').forEach(el=>el.classList.toggle('active',el.dataset.view===view));$('page-label').textContent={chat:'Preguntar',editor:'Documentar',incident:'Registrar un error',library:'Mi documentación',sharing:'Importar y compartir',admin:'Catálogos'}[view];if(view==='incident'&&typeof populateIncidentCatalog==='function')populateIncidentCatalog();if(view==='library'&&refresh)loadLibrary();if(view==='sharing'&&typeof loadGuideStatus==='function')loadGuideStatus();if(view==='admin'&&typeof loadAdmin==='function')loadAdmin();window.scrollTo(0,0);if(typeof recordNavigation==='function')recordNavigation(view);}
document.querySelectorAll('[data-view]').forEach(el=>el.addEventListener('click',()=>{if(typeof navigateModule==='function'){navigateModule(el.dataset.view);return;}if(el.dataset.view==='editor'){startNewDocument();return;}showView(el.dataset.view);}));
function getData(){const data={};fields.forEach(key=>{const input=form.elements.namedItem(key);data[key]=input.type==='checkbox'?input.checked:input.value.trim();});data.notes=$('notes').value;data.is_new_error=false;data.error_code='';return data;}
function setData(data){$('notes-result').classList.add('hidden');fields.forEach(key=>form.elements.namedItem(key).classList.remove('ai-filled'));fields.forEach(key=>{const input=form.elements.namedItem(key),value=data[key]||(key==='project'?'General':key==='kind'?'service':'');if(input.type==='checkbox'){input.checked=Boolean(data[key]);return;}if(input.tagName==='SELECT'&&value&&![...input.options].some(option=>option.value===value)){const option=node('option',value+' (actual)');option.value=value;input.append(option);}input.value=value;});$('notes').value=data.notes||'';renderHelp();renderPreview();}
function setStep(number){step=number;document.querySelectorAll('.form-step').forEach(el=>el.classList.toggle('hidden',el.id!==`step-${number}`));document.querySelectorAll('.step').forEach(el=>{el.classList.toggle('active',Number(el.dataset.step)===number);el.setAttribute('aria-selected',String(Number(el.dataset.step)===number));});$('previous').classList.toggle('hidden',number===1);$('next').classList.toggle('hidden',number===3);if(number===3)renderPreview();if(typeof recordNavigation==='function'&&!$('view-editor').classList.contains('hidden'))recordNavigation('editor');}
document.querySelectorAll('[data-step]').forEach(el=>el.addEventListener('click',()=>setStep(Number(el.dataset.step))));
$('previous').addEventListener('click',()=>setStep(Math.max(1,step-1)));
$('next').addEventListener('click',()=>setStep(Math.min(3,step+1)));
function renderHelp(){const data=getData();$('questions').replaceChildren();Object.entries(questions).filter(([key])=>!data[key]).forEach(([key,text])=>{const b=node('button','↗ '+text,'help-question');b.type='button';b.addEventListener('click',()=>{setStep(['owner','purpose'].includes(key)?1:2);form.elements.namedItem(key).focus();});$('questions').append(b);});if(!$('questions').children.length)$('questions').append(node('p','Ya cubriste las secciones principales. Revisa que los datos sean correctos.'));}
function renderPreview(){const d=getData(),target=$('document-preview');target.replaceChildren(node('h1',d.name||'Tu documento'),node('p',[d.project,d.service,d.kind,d.area||'Área por completar',d.topic,d.owner&&`Responsable: ${d.owner}`,d.is_new_error&&'Error nuevo',d.error_code].filter(Boolean).join(' · ')));Object.entries(labels).forEach(([key,title])=>{target.append(node('h2',title),node('p',d[key]||'Todavía no documentado.',d[key]?'':'empty'));});}
function markDirty(event){if(event?.target?.classList)event.target.classList.remove('ai-filled');dirty=true;$('draft-state').textContent='Cambios sin guardar';renderHelp();}
form.addEventListener('input',markDirty);$('notes').addEventListener('input',markDirty);
$('example').addEventListener('click',()=>{if($('notes').value&&!confirm('¿Reemplazar tus notas por el ejemplo ficticio?'))return;$('notes').value='Área: Pagos. Microservicio: ms-payment. Responsable: Equipo de integraciones. Consulta el estado de los pagos. Depende de una pasarela de pagos. Proyecto: DemoShop. Para consultar un pago se utiliza GET /payments/{id}.';markDirty();notify('Ejemplo ficticio cargado. Ahora puedes organizar las notas.');});
$('organize').addEventListener('click',async()=>{
  const epoch=documentEpoch;
  const notes=$('notes').value.trim();
  if(notes.length<20){notify('Cuéntanos un poco más: escribe al menos una explicación breve.',true);$('notes').focus();return;}
  if(fields.filter(key=>!['project','kind','is_new_error'].includes(key)).some(key=>form.elements.namedItem(key).value.trim())&&!confirm('La ayuda completará solo los campos vacíos. Tus datos actuales se conservarán. ¿Continuar?'))return;
  const button=$('organize');button.disabled=true;button.textContent='Organizando en tu equipo…';
  try{
    const result=await api('/api/v1/documentation/organize',{method:'POST',body:JSON.stringify({notes})});
    if(epoch!==documentEpoch)return;
    const existing=getData();
    const combined={...existing};fields.forEach(key=>{if((!existing[key]||(key==='project'&&existing[key]==='General'))&&result.data[key])combined[key]=result.data[key];});const completed=fields.filter(key=>combined[key]!==existing[key]);setData(combined);completed.forEach(key=>form.elements.namedItem(key).classList.add('ai-filled'));
    markDirty();setStep(1);$('notes-result').textContent=completed.length?'Se completaron '+completed.length+' campos, resaltados en violeta. Revisa los datos antes de guardar.':'No encontramos nuevos datos para completar. Puedes añadir detalles directamente en el formulario.';$('notes-result').classList.remove('hidden');notify('Formulario completado. Revisa los datos antes de guardar.');
  }catch(error){notify(error.message,true);}finally{button.disabled=false;button.textContent='Completar campos con mis notas';}
});
async function saveDraft(){const epoch=documentEpoch,data=getData();if(!data.area||!data.name){setStep(1);notify('Completa el área y el título para guardar.',true);form.elements.namedItem(!data.area?'area':'name').focus();return false;}const button=$('save');button.disabled=true;try{const url=currentDraft?`/api/v1/drafts/${currentDraft.id}`:'/api/v1/drafts';const payload=currentDraft?{revision:currentDraft.revision,data}:data;const saved=await api(url,{method:currentDraft?'PUT':'POST',body:JSON.stringify(payload)});if(epoch!==documentEpoch)return false;currentDraft=saved;dirty=false;$('draft-state').textContent='Borrador guardado';$('saved-at').textContent='Guardado solo en este equipo';return true;}catch(error){notify(error.message,true);return false;}finally{button.disabled=false;}}
form.addEventListener('submit',async event=>{event.preventDefault();if(await saveDraft())notify('Borrador guardado para continuar después. Todavía no está incorporado a la guía ni enviado a Git.');});
function markdown(data){let text=`# ${data.name||'Documento por identificar'}\n\nProyecto: ${data.project||'General'}\nServicio: ${data.service||data.name||'General'}\nTipo: ${data.kind}\nÁrea: ${data.area||'Por confirmar'}\nTema: ${data.topic||'Por confirmar'}\nResponsable: ${data.owner||'Por confirmar'}\n`;Object.entries(labels).forEach(([key,title])=>text+=`\n## ${title}\n\n${data[key]||'Pendiente de documentar.'}\n`);return text;}
$('download').addEventListener('click',()=>{const data=getData(),blob=new Blob([markdown(data)],{type:'text/markdown;charset=utf-8'}),url=URL.createObjectURL(blob),a=node('a');a.href=url;a.download=(data.name||'microservicio').replace(/[^a-zA-Z0-9_-]/g,'-')+'.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notify('Documento descargado para revisión.');});
function startNewDocument(){
  if(dirty&&!confirm('Tienes cambios sin guardar. ¿Descartarlos y empezar un documento nuevo? Los borradores guardados se conservan.'))return;
  documentEpoch++;currentDraft=null;dirty=false;setData({});
  if(typeof applyCatalogs==='function')applyCatalogs();
  $('notes-assistant').open=false;form.querySelectorAll('details').forEach(detail=>detail.open=false);
  setStep(1);$('draft-state').textContent='Nuevo borrador';$('saved-at').textContent='Borrador local · no enviado a Git';showView('editor');
}
$('new-document').addEventListener('click',startNewDocument);
$('start-new-document').addEventListener('click',startNewDocument);
function renderMarkdown(text,target){target.replaceChildren();let code=null;for(const line of text.split('\n')){if(/^\s*```/.test(line)){if(code){target.append(code);code=null;}else code=node('pre','');continue;}if(code){code.textContent+=line+'\n';continue;}const heading=/^(#{1,3})\s+(.+)/.exec(line);target.append(heading?node('h'+heading[1].length,heading[2]):node('p',line));}if(code)target.append(code);}
async function loadLibrary(){const request=++libraryRequest;libraryLoading=true;$('library-detail').classList.add('hidden');renderLibrary();try{const [snapshot,drafts]=await Promise.all([api('/api/v1/knowledge/snapshot'),api('/api/v1/drafts')]);if(request!==libraryRequest)return;official=snapshot.documents;draftList=drafts;$('doc-count').textContent=String(official.length);if(typeof updateProjectFilter==='function')updateProjectFilter();libraryLoading=false;renderLibrary();}catch(error){if(request!==libraryRequest)return;libraryLoading=false;notify(error.message,true);$('library-list').replaceChildren(node('p','No pudimos cargar los documentos. Intenta de nuevo.','empty-state'));}}
function renderLibrary(){
  $('view-library').classList.toggle('review-mode',['pending','deletions'].includes(libraryMode));
  $('project-filter').classList.toggle('hidden',['pending','deletions'].includes(libraryMode));
  if(libraryLoading){$('library-list').replaceChildren(node('p','Cargando documentos…','empty-state'));return;}
  if(['pending','deletions'].includes(libraryMode)){renderProposals();return;}
  if(typeof renderFolderLibrary==='function'){renderFolderLibrary();return;}
  const search=$('library-search').value.toLocaleLowerCase('es'),target=$('library-list');
  target.replaceChildren();$('library-detail').classList.add('hidden');
  const selected=$('project-filter').value,items=libraryMode==='official'?official:draftList;
  items.filter(item=>(!selected||documentProject(item)===selected)&&JSON.stringify(item).toLocaleLowerCase('es').includes(search)).forEach(item=>{
    const b=node('button',undefined,'library-card');b.type='button';
    if(libraryMode==='official'){
      const title=item.content.split('\n').find(line=>line.startsWith('# '))?.slice(2)||item.path;
      b.append(node('span','▤','card-icon teal'),node('h3',title),node('p',documentProject(item)+' · Disponible en tu guía'),node('small',item.path));
      b.addEventListener('click',()=>{renderMarkdown(item.content,$('library-detail'));$('library-detail').append(node('small','Fuente: '+item.path+' · Versión '+item.commit.slice(0,12)));$('library-detail').classList.remove('hidden');$('library-detail').scrollIntoView({behavior:'smooth',block:'start'});});
    }else{
      b.append(node('span','✎','card-icon violet'),node('h3',item.data.name),node('p',documentProject(item)+' · '+item.data.area+' · Borrador'),node('small','Actualizado '+new Date(item.updated_at).toLocaleString('es')));
      b.addEventListener('click',()=>{if(dirty&&!confirm('¿Dejar los cambios sin guardar y abrir este borrador?'))return;currentDraft=item;setData(item.data);dirty=false;setStep(1);$('draft-state').textContent='Borrador guardado';showView('editor');});
    }target.append(b);
  });
  if(!target.children.length)target.append(node('div',libraryMode==='drafts'?'Aún no tienes borradores. Empieza por contar lo que sabes.':'No encontramos documentos con esa búsqueda.','empty-state'));
}
function libraryTab(mode){libraryMode=mode;$('official-tab').classList.toggle('active',mode==='official');$('drafts-tab').classList.toggle('active',mode==='drafts');$('pending-tab').classList.toggle('active',mode==='pending');$('deletions-tab').classList.toggle('active',mode==='deletions');$('project-filter').disabled=['pending','deletions'].includes(mode);renderLibrary();if(typeof recordNavigation==='function')recordNavigation('library');}
$('official-tab').addEventListener('click',()=>libraryTab('official'));$('drafts-tab').addEventListener('click',()=>libraryTab('drafts'));$('library-search').addEventListener('input',renderLibrary);
function addMessage(text,who){const el=node('div',undefined,'message '+who);el.append(node('strong',who==='user'?'Tú':'Support AI','message-label'),node('div',text));$('messages').append(el);return el;}
let chatEpoch=0,chatAbort=null;
function chatHome(clear=false){
  if(chatAbort){chatAbort.abort();chatAbort=null;chatEpoch++;document.querySelectorAll('.message.loading').forEach(message=>{message.classList.remove('loading');message.lastElementChild.textContent='Consulta interrumpida. Puedes hacer otra pregunta.';});}
  if(clear){chatEpoch++;$('messages').replaceChildren();}$('question').value='';
  $('send').disabled=false;$('chat-welcome').classList.remove('hidden');$('messages').classList.add('hidden');$('chat-return').classList.add('hidden');
}
async function ask(question){
  const epoch=++chatEpoch;chatAbort=new AbortController();
  $('chat-welcome').classList.add('hidden');$('messages').classList.remove('hidden');$('chat-return').classList.remove('hidden');
  if(typeof recordNavigation==='function')recordNavigation('chat');
  addMessage(question,'user');const message=addMessage('Buscando en tus documentos…','loading');$('send').disabled=true;
  try{const result=await api('/api/v1/chat',{method:'POST',body:JSON.stringify({question}),signal:chatAbort.signal});if(epoch!==chatEpoch)return;
    message.classList.remove('loading');message.lastElementChild.textContent=result.answer;
    if(result.sources.length){const details=node('details'),summary=node('summary',`Ver ${result.sources.length} fuentes`);details.append(summary);result.sources.forEach((source,i)=>{const block=node('div',undefined,'source-item');block.append(node('strong',`[${i+1}] ${source.path} · líneas ${source.start_line}–${source.end_line}`),node('p',source.quote),node('small','Versión '+source.commit.slice(0,12)));details.append(block);});message.append(details);}
  }catch(error){if(epoch!==chatEpoch||error.name==='AbortError')return;message.classList.remove('loading');message.lastElementChild.textContent=error.message;notify('Si aún no preparaste los documentos, usa Actualizar conocimiento.',true);}
  finally{if(epoch===chatEpoch){chatAbort=null;$('send').disabled=false;if(!$('view-chat').classList.contains('hidden')&&$('chat-welcome').classList.contains('hidden')){$('question').focus();message.scrollIntoView({behavior:'smooth',block:'nearest'});}}}
}
$('chat-return').addEventListener('click',()=>{chatHome();if(typeof recordNavigation==='function')recordNavigation('chat');window.scrollTo(0,0);});
$('chat-form').addEventListener('submit',event=>{event.preventDefault();const question=$('question').value.trim();if(question.length<3||$('send').disabled)return;$('question').value='';ask(question);});$('question').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();$('chat-form').requestSubmit();}});
document.querySelectorAll('[data-question]').forEach(button=>button.addEventListener('click',()=>{if(!$('send').disabled){$('question').value=button.dataset.question;$('chat-form').requestSubmit();}}));
$('prepare').addEventListener('click',async()=>{const button=$('prepare');button.disabled=true;button.textContent='Preparando tus documentos…';try{const result=await api('/api/v1/workspace/prepare',{method:'POST'});notify(`Conocimiento actualizado: ${result.documents} documentos disponibles.`);}catch(error){notify(error.message,true);}finally{button.disabled=false;button.textContent='Actualizar conocimiento ↻';}});
window.addEventListener('beforeunload',event=>{if(dirty||(typeof incidentDirty!=='undefined'&&incidentDirty)||(typeof catalogDirty!=='undefined'&&catalogDirty)||(typeof libraryEditorDirty!=='undefined'&&libraryEditorDirty)){event.preventDefault();event.returnValue='';}});
setStep(1);renderHelp();api('/api/v1/knowledge/snapshot').then(data=>{$('doc-count').textContent=String(data.documents.length);}).catch(()=>{});
