'use strict';
let catalogEntries=[];
let catalogRevision=1, folderPath=[], folderMode='';
let libraryLayout='grid',openDocumentPath=null,libraryEditorDirty=false,libraryEditorOpen=false,catalogDirty=false;
function fileExplorerIcon(folder=true){
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 48 40');svg.setAttribute('aria-hidden','true');svg.classList.add('explorer-icon');
  const shapes=folder?[
    ['M4 7a4 4 0 0 1 4-4h11l5 5h16a4 4 0 0 1 4 4v20a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4Z','#c9a567'],
    ['M4 15a4 4 0 0 1 4-4h32a4 4 0 0 1 4 4v17a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4Z','#e6c68a'],
  ]:[['M12 3h17l9 9v22a3 3 0 0 1-3 3H12a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3Z','#dceadf'],['M29 3v9h9M16 19h15M16 25h15M16 31h10','none']];
  shapes.forEach(([d,fill])=>{const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',d);path.setAttribute('fill',fill);if(fill==='none'){path.setAttribute('stroke','#70947b');path.setAttribute('stroke-width','2');path.setAttribute('stroke-linecap','round');}svg.append(path);});return svg;
}
const libraryContent=node('div',undefined,'library-content');
$('library-list').before(libraryContent);libraryContent.append($('library-list'),$('library-detail'));
const catalogNames={projects:'Proyectos',services:'Servicios',areas:'Áreas',teams:'Equipos responsables',types:'Tipos de documento'};
const catalogDetails={projects:['proyecto','▰','Agrupa los servicios y documentos de un mismo proyecto.','Ej. admon-canales'],services:['servicio','⬡','Relaciona un servicio con el proyecto al que pertenece.','Ej. ms-canales'],areas:['área','◈','Organiza el conocimiento por área de negocio.','Ej. Canales digitales'],teams:['equipo','♧','Identifica al equipo responsable de la documentación.','Ej. Equipo de integraciones'],types:['tipo','▤','Define cómo se clasifica un documento.','Ej. Guía de integración']};
const typeNames={project:'Guía del proyecto',service:'Microservicio',api:'API y endpoints',incident:'Error o incidente',procedure:'Procedimiento'};
form.elements.namedItem('name').closest('label').firstChild.textContent='Título del documento ';
form.elements.namedItem('name').placeholder='Ej. Integración de la pasarela de pagos';
const knownErrors=form.elements.namedItem('errors').closest('label');form.querySelector('.extra-fields').append(knownErrors);form.querySelector('.extra-fields summary').textContent='Información adicional: configuración, CORS y fallos conocidos';
function typeValue(entry){return Object.keys(typeNames).find(key=>typeNames[key]===entry.name)||entry.name;}
function fillSelect(select,entries,current='',placeholder='Seleccionar…'){
  select.replaceChildren();const blank=node('option',placeholder);blank.value='';select.append(blank);
  entries.forEach(entry=>{const option=node('option',entry.name);option.value=entry.value||entry.name;select.append(option);});
  if(current&&![...select.options].some(option=>option.value===current)){
    const previous=node('option',(typeNames[current]||current)+' (actual)');previous.value=current;select.append(previous);
  }
  select.value=current;
}
function applyCatalogs(){
  const selected=getData();
  for(const [field,category] of Object.entries({project:'projects',area:'areas',owner:'teams',kind:'types'})){
    let select=form.elements.namedItem(field);
    if(select.tagName!=='SELECT'){const replacement=node('select');replacement.name=field;select.replaceWith(replacement);select=replacement;}
    const entries=catalogEntries.filter(entry=>entry.category===category&&entry.active&&(category!=='types'||typeValue(entry)!=='incident'))
      .map(entry=>({...entry,value:category==='types'?typeValue(entry):entry.name}));
    fillSelect(select,entries,selected[field],field==='owner'?'Responsable por asignar':'Seleccionar…');
  }
  refreshServices(selected.service);
  $('catalog-hint').textContent=catalogEntries.some(entry=>entry.category==='projects'&&entry.active)?
    'Elige las opciones o agrega las que falten en Catálogos.':
    'Puedes agregar proyectos, áreas y servicios en Catálogos.';
}
function refreshServices(current=''){
  const project=form.elements.namedItem('project').value;
  const parent=catalogEntries.find(entry=>entry.category==='projects'&&entry.name===project&&entry.active);
  fillSelect(form.elements.namedItem('service'),catalogEntries.filter(entry=>entry.category==='services'&&entry.active&&entry.project_id===parent?.id),current,'General del proyecto / por definir');
}
form.addEventListener('change',event=>{
  if(event.target.name==='project')refreshServices();

});
async function loadAdmin(){
  try{
    catalogEntries=await api('/api/v1/catalogs');
    applyCatalogs();renderCatalog();if(typeof populateIncidentCatalog==='function')populateIncidentCatalog();
  }catch(error){notify(error.message,true);}
}
$('admin-review').addEventListener('click',()=>{libraryMode='pending';showView('library');libraryTab('pending');});
function resetCatalog(){catalogDirty=false;
  $('catalog-id').value='';$('catalog-name').value='';$('catalog-active').checked=true;catalogRevision=1;
  const [noun,,help,placeholder]=catalogDetails[$('catalog-category').value];
  $('catalog-form-title').textContent=(noun==='área'?'Nueva ':'Nuevo ')+noun;$('catalog-form-mode').textContent='NUEVA OPCIÓN';
  $('catalog-form-help').textContent=help;$('catalog-name').placeholder=placeholder;$('catalog-save').textContent='Crear '+noun;$('catalog-new').textContent='Limpiar';
  document.querySelectorAll('.catalog-entry').forEach(row=>row.setAttribute('aria-pressed','false'));
  fillSelect($('catalog-project'),catalogEntries.filter(entry=>entry.category==='projects'&&entry.active).map(entry=>({...entry,value:entry.id})));
  $('catalog-project-label').classList.toggle('hidden',$('catalog-category').value!=='services');
}
function renderCatalog(){
  const category=$('catalog-category').value,target=$('catalog-list');target.replaceChildren();
  const tabs=$('catalog-category-tabs');tabs.replaceChildren();
  Object.entries(catalogNames).forEach(([key,name])=>{
    const button=node('button',undefined,'catalog-category');button.type='button';button.setAttribute('role','tab');button.setAttribute('aria-selected',String(key===category));button.dataset.category=key;
    button.append(node('span',catalogDetails[key][1],'category-symbol'),node('span',name),node('small',String(catalogEntries.filter(entry=>entry.category===key).length)));
    button.addEventListener('click',()=>{if(key===category)return;$('catalog-category').value=key;$('catalog-category').dispatchEvent(new Event('change'));});tabs.append(button);
  });
  const entries=catalogEntries.filter(entry=>entry.category===category),search=$('catalog-search').value.trim().toLocaleLowerCase('es'),status=$('catalog-status').value;
  $('catalog-list-title').textContent=catalogNames[category];$('catalog-list-summary').textContent=`${entries.length} opciones · ${entries.filter(entry=>entry.active).length} disponibles`;
  $('catalog-add').textContent='+ '+(category==='areas'?'Nueva ':'Nuevo ')+catalogDetails[category][0];
  entries.filter(entry=>{
    const parent=catalogEntries.find(parent=>parent.id===entry.project_id);
    return (entry.name+' '+(parent?.name||'')).toLocaleLowerCase('es').includes(search)&&(status==='all'||Boolean(entry.active)===(status==='active'));
  }).forEach(entry=>{
    const button=node('button',undefined,'catalog-entry');button.type='button';
    const project=catalogEntries.find(parent=>parent.id===entry.project_id);
    button.setAttribute('aria-pressed',String($('catalog-id').value===entry.id));
    const name=node('div',undefined,'catalog-entry-name'),text=node('div');text.append(node('strong',entry.name));if(project)text.append(node('small',project.name));
    name.append(node('span',catalogDetails[category][1],'catalog-row-icon'),text);button.append(name,node('span',entry.active?'Disponible':'Inactiva','catalog-state '+(entry.active?'available':'inactive')),node('span','›','catalog-edit-arrow'));
    button.addEventListener('click',()=>{
      resetCatalog();$('catalog-id').value=entry.id;$('catalog-name').value=entry.name;$('catalog-active').checked=Boolean(entry.active);catalogRevision=entry.revision;
      $('catalog-project').value=entry.project_id||'';$('catalog-form-title').textContent='Editar '+catalogDetails[category][0];$('catalog-form-mode').textContent='EDITANDO OPCIÓN';$('catalog-save').textContent='Guardar cambios';$('catalog-new').textContent='Cancelar edición';renderCatalog();$('catalog-name').focus();
    });target.append(button);
  });
  if(!target.children.length)target.append(node('p',entries.length?'No encontramos opciones con estos filtros.':'Todavía no hay opciones. Crea la primera en el formulario.','empty-state'));
}
$('catalog-category').addEventListener('change',()=>{$('catalog-search').value='';$('catalog-status').value='all';resetCatalog();renderCatalog();if(typeof recordNavigation==='function'&&!$('view-admin').classList.contains('hidden'))recordNavigation('admin');});
$('catalog-search').addEventListener('input',renderCatalog);$('catalog-status').addEventListener('change',renderCatalog);
$('catalog-add').addEventListener('click',()=>{resetCatalog();$('catalog-name').focus();if(window.innerWidth<=900)$('catalog-form').scrollIntoView({behavior:'smooth',block:'start'});});
$('catalog-new').addEventListener('click',resetCatalog);
$('catalog-form').addEventListener('input',()=>catalogDirty=true);
$('catalog-form').addEventListener('submit',async event=>{
  event.preventDefault();const button=$('catalog-save');if(button.disabled)return;button.disabled=true;const id=$('catalog-id').value,category=$('catalog-category').value;
  const data={category,name:$('catalog-name').value.trim(),active:$('catalog-active').checked,revision:catalogRevision,project_id:category==='services'?$('catalog-project').value||null:null};
  try{await api('/api/v1/catalogs'+(id?'/'+id:''),{method:id?'PUT':'POST',body:JSON.stringify(data)});await loadAdmin();resetCatalog();notify('Catálogo actualizado. Ya está disponible para documentar.');}
  catch(error){notify(error.message,true);}
  finally{button.disabled=false;}
});
function documentInfo(item){
  if(item.data){const data=item.data;return {project:data.project||'General',service:data.service||data.name||'General',kind:typeNames[data.kind]||data.kind||'Documento',title:data.name,area:data.area};}
  const header=(item.content||'').split(/^## /m)[0];
  const value=key=>new RegExp('^'+key+':\\s*(.+)$','m').exec(header)?.[1]?.trim();
  const title=/^# (.+)$/m.exec(item.content||'')?.[1]||item.path.split('/').pop();
  return {project:value('Proyecto')||'General',service:value('Servicio')||title,kind:typeNames[value('Tipo')]||value('Tipo')||'Documento',title,area:value('Área')||''};
}
function renderFolderLibrary(){openDocumentPath=null;libraryEditorDirty=false;libraryEditorOpen=false;
  const target=$('library-list');target.replaceChildren();target.classList.add('folder-browser');$('library-detail').classList.add('hidden');
  if(folderMode!==libraryMode){folderMode=libraryMode;folderPath=[];}
  const search=$('library-search').value.trim().toLocaleLowerCase('es'),project=$('project-filter').value;
  const items=(libraryMode==='official'?official:draftList).filter(item=>(!project||documentInfo(item).project===project)&&(!search||JSON.stringify(item).toLocaleLowerCase('es').includes(search)));
  const nav=node('nav',undefined,'folder-breadcrumb');nav.setAttribute('aria-label','Ruta de carpetas');
  const root=node('button',libraryMode==='official'?'Mi documentación':'Mis borradores');root.type='button';root.addEventListener('click',()=>{folderPath=[];renderFolderLibrary();});nav.append(root);
  folderPath.forEach((part,index)=>{const button=node('button',part);button.type='button';button.addEventListener('click',()=>{folderPath=folderPath.slice(0,index+1);renderFolderLibrary();});nav.append(node('span','/'),button);});target.append(nav);
  const keys=['project','service','kind'];
  let visible=search?items:items.filter(item=>folderPath.every((part,index)=>documentInfo(item)[keys[index]]===part));
  const folders=!search&&folderPath.length<3;
  const names=folders?[...new Set(visible.map(item=>documentInfo(item)[keys[folderPath.length]]))]:[];
  const bar=node('div',undefined,'explorer-heading'),description=node('div');
  const documentCount=visible.length+' documento'+(visible.length===1?'':'s'),folderCount=names.length+' '+(names.length===1?['proyecto','servicio','tipo']:['proyectos','servicios','tipos'])[folderPath.length];
  description.append(node('h2',search?'Resultados de búsqueda':folders?['Tus proyectos','Servicios del proyecto','Tipos de documento'][folderPath.length]:'Documentos'),node('p',folders?folderCount+' · '+documentCount:documentCount));
  const layouts=node('div',undefined,'explorer-layouts');layouts.setAttribute('role','group');layouts.setAttribute('aria-label','Vista de documentos');
  [['grid','▦','Vista de tarjetas'],['list','☰','Vista de lista']].forEach(([value,icon,label])=>{const button=node('button',icon);button.type='button';button.setAttribute('aria-label',label);button.setAttribute('aria-pressed',String(libraryLayout===value));button.addEventListener('click',()=>{libraryLayout=value;renderFolderLibrary();});layouts.append(button);});
  bar.append(description,layouts);target.append(bar);
  if(typeof recordNavigation==='function'&&!$('view-library').classList.contains('hidden'))recordNavigation('library');
  if(!visible.length){target.append(node('p','No hay documentos aquí. Puedes cambiar la búsqueda, volver a una carpeta anterior o crear un documento.','empty-state'));return;}
  const grid=node('div',undefined,'folder-grid explorer-grid'+(libraryLayout==='list'?' explorer-list':''));target.append(grid);
  if(!search&&folderPath.length<3){
    const key=keys[folderPath.length];
    [...new Set(visible.map(item=>documentInfo(item)[key]))].sort((a,b)=>a.localeCompare(b,'es')).forEach(name=>{
      const count=visible.filter(item=>documentInfo(item)[key]===name).length;
      const button=node('button',undefined,'folder-card');button.type='button';button.setAttribute('aria-label','Abrir carpeta '+name);
      const icon=node('span',undefined,'explorer-icon-tile'),text=node('span',undefined,'explorer-folder-text');icon.append(fileExplorerIcon());
      text.append(node('strong',name),node('small',count+' documento'+(count===1?'':'s')));
      button.append(icon,text,node('span','›','explorer-arrow'));
      button.addEventListener('click',()=>{folderPath.push(name);renderFolderLibrary();});grid.append(button);
    });
  }else visible.forEach(item=>{
    const info=documentInfo(item),button=node('button',undefined,'library-card');button.type='button';
    const icon=node('span',undefined,'explorer-icon-tile document-tile');icon.append(fileExplorerIcon(false));
    button.append(icon,node('h3',info.title),node('p',[info.project,info.service].join(' · ')),node('small',[info.kind,info.area].filter(Boolean).join(' · ')));
    button.addEventListener('click',()=>{
      if(libraryMode==='official')openLibraryDocument(item);
      else{if(item.data.kind==='incident'&&typeof openIncidentDraft==='function'){openIncidentDraft(item);return;}if(dirty&&!confirm('¿Dejar los cambios sin guardar y abrir este borrador?'))return;currentDraft=item;setData(item.data);refreshServices(item.data.service);dirty=false;setStep(1);$('draft-state').textContent='Borrador guardado';showView('editor');}
    });grid.append(button);
  });
}
function openLibraryDocument(item){openDocumentPath=item.path;libraryEditorDirty=false;libraryEditorOpen=false;if(typeof recordNavigation==='function')recordNavigation('library');
  const target=$('library-detail');renderMarkdown(item.content,target);
  const actions=node('div',undefined,'review-actions'),edit=node('button','Editar documento','primary');edit.type='button';
  const remove=node('button','Eliminar documento','danger-button');remove.type='button';
  remove.addEventListener('click',async()=>{
    remove.disabled=true;remove.textContent='Preparando…';
    try{
      const result=await api('/api/v1/guide/delete',{method:'POST',body:JSON.stringify({path:item.path,base_sha256:item.sha256})});
      if(!result.proposal)throw new Error('No se pudo preparar la solicitud.');
      target.classList.add('hidden');$('library-search').value='';selectedProposal=null;libraryTab('deletions');
      await renderProposals();await openProposal(result.proposal.id);
      notify('Solicitud preparada. El documento se conserva hasta justificar y confirmar su eliminación.');
    }catch(error){notify(error.message,true);remove.disabled=false;remove.textContent='Eliminar documento';}
  });
  edit.addEventListener('click',()=>editLibraryDocument(item));actions.append(edit,remove);target.prepend(actions);
  target.append(node('small','Archivo: '+item.path+' · Versión '+item.commit.slice(0,12)));target.classList.remove('hidden');target.scrollIntoView({behavior:'smooth',block:'start'});
}
function editLibraryDocument(item){libraryEditorDirty=false;libraryEditorOpen=true;if(typeof recordNavigation==='function')recordNavigation('library');
  const target=$('library-detail');target.replaceChildren(node('span','ACTUALIZAR CONOCIMIENTO','eyebrow'),node('h1','Editar documento'),node('p','Edita por secciones. Guardar actualiza tu guía local y no envía cambios a Git ni a un PR.','muted'));
  const editor=node('form'),input=node('textarea');input.id='edit-document-content';input.value=item.content;input.readOnly=true;
  const sections=[];let offset=0,fence=null;
  for(const line of item.content.split(/(?<=\n)/)){
    const marker=/^ {0,3}(`{3,}|~{3,})/.exec(line);
    if(marker){if(!fence)fence=marker[1];else if(marker[1][0]===fence[0]&&marker[1].length>=fence.length)fence=null;}
    if(!fence&&/^## /.test(line))sections.push({start:offset,bodyStart:offset+line.length,title:line.replace(/^## /,'').trim()});
    offset+=line.length;
  }
  const headerEnd=sections[0]?.start??0,originalHeader=item.content.slice(0,headerEnd);
  const metadata=[],grid=node('div',undefined,'field-grid edit-identification');
  if(sections.length){
    const titleLabel=node('label','Título del documento'),title=node('input');title.value=/^# (.+)$/m.exec(originalHeader)?.[1]||documentInfo(item).title;titleLabel.append(title);grid.append(titleLabel);metadata.push({key:'#',control:title,original:title.value});
    for(const [key,category] of [['Proyecto','projects'],['Servicio','services'],['Tipo','types'],['Área','areas'],['Responsable','teams'],['Tema',null],['Código de error',null],...(/^Tipo: incident$/m.test(originalHeader)?[['Ambiente',null],['Estado','incident-states']]:[])]){
      const label=node('label',key),select=node(category?'select':'input'),value=originalHeader.split(/\r?\n/).find(line=>line.startsWith(key+':'))?.slice(key.length+1).trim()||'';
      select.setAttribute('aria-label',key);
      const entries=category==='incident-states'?[{name:'En investigación'},{name:'Resuelto'}]:catalogEntries.filter(entry=>entry.category===category&&entry.active).map(entry=>({...entry,value:category==='types'?typeValue(entry):entry.name}));
      if(category)fillSelect(select,entries,value,'Sin especificar');else select.value=value;label.append(select);grid.append(label);metadata.push({key,control:select,original:value});
    }
    editor.append(node('h2','Identificación'),grid,node('h2','Contenido del documento'));
  }
  const bodies=[];
  if(!sections.length){
    const label=node('label','Contenido del documento'),body=node('textarea');body.rows=12;body.value=item.content;body.className='section-editor';label.append(body);editor.append(label);bodies.push({start:0,end:item.content.length,control:body,original:body.value});
  }
  sections.forEach((section,index)=>{
    const end=sections[index+1]?.start??item.content.length,details=node('details',undefined,'edit-section'),summary=node('summary',section.title),label=node('label','Detalle'),body=node('textarea');
    body.value=item.content.slice(section.bodyStart,end);body.rows=Math.min(12,Math.max(4,body.value.split('\n').length));body.className='section-editor';body.setAttribute('aria-label',section.title);
    details.open=index===0;label.append(body);details.append(summary,label);editor.append(details);bodies.push({start:section.bodyStart,end,control:body,original:body.value});
  });
  function content(){
    let header=originalHeader;
    for(const {key,control,original} of metadata){
      if(control.value===original)continue;
      const expression=key==='#'?/^# [^\n]*/m:new RegExp('^'+key+':[^\\n]*','m');
      const line=key==='#'?'# '+control.value:key+': '+control.value;
      header=expression.test(header)?header.replace(expression,()=>line):header.trimEnd()+'\n'+line+'\n\n';
    }
    let result=item.content;
    for(const body of [...bodies].reverse())if(body.control.value!==body.original){let value=body.control.value;if(body.end<item.content.length&&!value.endsWith('\n'))value+='\n';result=result.slice(0,body.start)+value+result.slice(body.end);}
    if(sections.length)result=header+result.slice(headerEnd);
    input.value=result;return result;
  }
  editor.addEventListener('input',()=>{libraryEditorDirty=true;content();});editor.addEventListener('change',()=>{libraryEditorDirty=true;content();});
  const source=node('details',undefined,'edit-section source-view');source.append(node('summary','Ver Markdown generado (opcional)'),input);editor.append(source);
  const actions=node('div',undefined,'review-actions'),save=node('button','Guardar cambios locales','primary'),cancel=node('button','Cancelar','secondary'),preview=node('button','Vista previa','secondary'),rendered=node('article',undefined,'document-preview');save.type='submit';cancel.type=preview.type='button';
  cancel.addEventListener('click',()=>{if(content()!==item.content&&!confirm('¿Descartar la edición sin guardar?'))return;openLibraryDocument(item);});
  preview.addEventListener('click',()=>renderMarkdown(content(),rendered));actions.append(cancel,preview,save);editor.append(node('p','Los cambios se guardan en tu guía local. La revisión del líder ocurre en el PR.','draft-notice'),actions,rendered);target.append(editor);
  editor.addEventListener('submit',async event=>{
    event.preventDefault();save.disabled=true;
    try{
      const edited=content();
      if(edited===item.content){openLibraryDocument(item);notify('No hay cambios que guardar.');return;}
      save.textContent='Guardando…';
      const result=await api('/api/v1/guide/edit',{method:'POST',body:JSON.stringify({path:item.path,base_sha256:item.sha256,content:edited})});
      let proposal=result.created[0];
      if(!proposal){
        const pending=await api('/api/v1/guide/proposals');
        for(const row of pending.filter(row=>row.path===item.path)){
          const detail=await api('/api/v1/guide/proposals/'+row.id);
          if(detail.content===edited){proposal=detail;break;}
        }
      }
      if(!proposal)throw new Error('No se encontró el cambio para guardar. Vuelve a abrir el documento.');
      const saved=await api(`/api/v1/guide/proposals/${proposal.id}/approve`,{method:'POST',body:JSON.stringify({reviewed:true})});
      libraryMode='official';await loadLibrary();
      const updated=official.find(document=>document.path===item.path);
      $('project-filter').value='';$('library-search').value='';
      if(updated){const info=documentInfo(updated);folderMode='official';folderPath=[info.project,info.service,info.kind];}
      libraryTab('official');if(updated)openLibraryDocument(updated);
      notify(saved.index_error?'Cambios guardados. La búsqueda requiere atención: '+saved.index_error:'Cambios guardados en tu guía local. Puedes incluirlos en tu próximo commit y PR.');
    }
    catch(error){notify(error.message,true);}finally{save.disabled=false;save.textContent='Guardar cambios locales';}
  });
}
loadAdmin().then(resetCatalog);
