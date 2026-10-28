'use strict';
function documentProject(item) {
  if (item.data) return item.data.project || 'General';
  return /^Proyecto:\s*(.+)$/m.exec(item.content || '')?.[1]?.trim() || 'General';
}
function updateProjectFilter() {
  const select=$('project-filter'), current=select.value;
  select.replaceChildren(node('option','Todos los proyectos'));
  select.firstChild.value='';
  [...new Set([...official,...draftList].map(documentProject))].sort().forEach(project=>{
    const option=node('option',project);option.value=project;select.append(option);
  });
  if([...select.options].some(option=>option.value===current))select.value=current;
}
$('project-filter').addEventListener('change',renderLibrary);
$('pending-tab').addEventListener('click',()=>libraryTab('pending'));
$('deletions-tab').addEventListener('click',()=>libraryTab('deletions'));
async function loadGuideStatus() {
  try {
    const status=await api('/api/v1/guide/status');
    $('guide-mode').textContent=status.mode==='light'?'Modo ligero · Sin embeddings':'Búsqueda semántica';
    $('guide-size').textContent=`${status.documents} documentos aprobados · ${(status.text_bytes/1024).toFixed(1)} KB de texto · ${status.pending} cambios por revisar`;
    $('guide-refresh-status').textContent=status.last_error?`Última comprobación: ${status.last_error}`:'La revisión automática está '+(status.auto_refresh?'activa.':'desactivada en esta sesión.');
  }catch(error){notify(error.message,true);}
}
let selectedProposal=null, proposalRequest=0;
async function renderProposals() {
  const view=libraryMode;
  const target=$('library-list');target.className='library-grid pending-list';target.replaceChildren(node('p','Buscando cambios…','empty-state'));
  try {
    const all=await api('/api/v1/guide/proposals');if(libraryMode!==view)return;target.replaceChildren();
    const pending=all.filter(item=>item.deletion===(view==='deletions'));
    const search=$('library-search').value.toLowerCase();
    const filtered=pending.filter(item=>JSON.stringify(item).toLowerCase().includes(search));
    const heading=node('div',undefined,'pending-heading');heading.append(node('strong',view==='deletions'?'Eliminaciones pendientes':'Cambios locales'),node('span',String(filtered.length),'pending-count'));target.append(heading);
    target.append(node('p',view==='deletions'?'El documento se conserva hasta que indiques el motivo y confirmes.':'Revisa e incorpora a tu guía. La aprobación del equipo ocurre en el PR.','pending-caption'));
    filtered.forEach(item=>{
      const button=node('button',undefined,'pending-row');button.type='button';button.dataset.proposalId=item.id;button.setAttribute('aria-pressed',String(selectedProposal===item.id));
      const text=node('div',undefined,'pending-row-text'),status=item.deletion?'Eliminar':item.base_sha256?'Actualización':'Nuevo';
      text.append(node('h3',item.path.split('/').pop()),node('p',item.origin),node('span',status,'change-badge '+(item.deletion?'removal':item.base_sha256?'update':'addition')));
      button.append(node('span',item.deletion?'−':item.base_sha256?'↻':'+','change-icon'),text,node('span','›','row-arrow'));
      button.addEventListener('click',()=>openProposal(item.id));target.append(button);
    });
    if(!filtered.length)target.append(node('p',pending.length?'No hay coincidencias. Prueba otra búsqueda.':'Todo al día. No tienes cambios por incorporar.','empty-state'));
    if(!filtered.some(item=>item.id===selectedProposal)||$('library-detail').classList.contains('hidden')){
      selectedProposal=null;const detail=$('library-detail');detail.replaceChildren(node('span','▤','review-placeholder-icon'),node('h2',filtered.length?'Selecciona un cambio':'Tu guía está al día'),node('p',filtered.length?'Aquí verás el contenido y las acciones para incorporarlo.':'Los próximos cambios aparecerán en esta lista.'));detail.classList.remove('hidden');detail.classList.add('review-placeholder');
    }
  }catch(error){notify(error.message,true);}
}
async function openProposal(id) {
  const request=++proposalRequest;selectedProposal=id;
  document.querySelectorAll('.pending-row').forEach(row=>row.setAttribute('aria-pressed',String(row.dataset.proposalId===id)));
  try {
    const proposal=await api('/api/v1/guide/proposals/'+id),target=$('library-detail');
    if(request!==proposalRequest||!['pending','deletions'].includes(libraryMode))return;
    if(typeof recordNavigation==='function')recordNavigation('library');
    target.classList.remove('review-placeholder');
    const header=node('div',undefined,'review-document-heading');header.append(node('span','REVISIÓN LOCAL','eyebrow'),node('h1','Revisar cambio'),node('strong',proposal.path.split('/').pop()),node('p',proposal.path,'review-path'));target.replaceChildren(header);
    if(proposal.previous_content&&!proposal.deletion){const previous=node('details');previous.append(node('summary','Ver versión actual de la guía'));const body=node('div');renderMarkdown(proposal.previous_content,body);previous.append(body);target.append(previous);}
    target.append(node('h2',proposal.deletion?'Documento que se eliminará':'Contenido actualizado'));const preview=node('div',undefined,'review-content');renderMarkdown(proposal.deletion?proposal.previous_content:proposal.content,preview);target.append(preview);
    const label=node('label',undefined,'review-confirmation'),check=node('input');check.type='checkbox';check.id='reviewed-document';label.append(check,document.createTextNode(proposal.deletion?' He revisado esta retirada y quiero eliminar el documento de la guía.':' He revisado el contenido y quiero incorporarlo a mi guía.'));
    const approve=node('button',proposal.deletion?'Confirmar eliminación':'Incorporar a mi guía local',proposal.deletion?'danger-button':'primary');approve.id='approve-proposal';approve.disabled=true;
    let reason,confirmation;
    const updateConfirmation=()=>approve.disabled=!check.checked||(proposal.deletion&&(reason.value.trim().length<10||confirmation.value.trim().toUpperCase()!=='ELIMINAR'));
    check.addEventListener('change',updateConfirmation);
    const justification=node('div',undefined,'deletion-fields');
    if(proposal.deletion){
      const reasonLabel=node('label','¿Por qué se elimina este documento?'),confirmLabel=node('label','Escribe ELIMINAR para confirmar');
      reason=node('textarea');reason.id='deletion-reason';reason.rows=3;reason.maxLength=2000;reason.placeholder='Ej. Este procedimiento fue reemplazado por la guía de canales v2.';
      confirmation=node('input');confirmation.id='deletion-confirmation';confirmation.autocomplete='off';
      reason.addEventListener('input',updateConfirmation);confirmation.addEventListener('input',updateConfirmation);
      reasonLabel.append(reason,node('small','Mínimo 10 caracteres. El motivo quedará registrado para incluirlo en el PR.'));confirmLabel.append(confirmation);justification.append(reasonLabel,confirmLabel);
    }
    approve.addEventListener('click',async()=>{
      approve.disabled=true;approve.textContent='Guardando y actualizando la guía…';
      try{const result=await api(`/api/v1/guide/proposals/${id}/approve`,{method:'POST',body:JSON.stringify({reviewed:true,...(proposal.deletion?{reason:reason.value.trim(),confirmation_text:confirmation.value}: {})})});notify(result.index_error?'Cambio guardado. La búsqueda requiere atención: '+result.index_error:proposal.deletion?'Documento eliminado. El motivo quedó registrado en deletions/ para tu commit y PR.':'Documento incorporado. Ya puedes preguntarle al chat.');await loadLibrary();}
      catch(error){notify(error.message,true);approve.textContent=proposal.deletion?'Confirmar eliminación':'Incorporar a mi guía local';updateConfirmation();}
    });
    const footer=node('div',undefined,'review-footer'),actions=node('div',undefined,'review-actions');actions.append(approve);if(proposal.deletion)footer.append(justification);footer.append(label,actions);target.append(footer);target.classList.remove('hidden');if(window.innerWidth<=900)target.scrollIntoView({behavior:'smooth',block:'start'});
    {
      const reject=node('button',proposal.deletion?'Cancelar eliminación':'Rechazar propuesta','secondary');reject.type='button';reject.addEventListener('click',async()=>{
        if(!confirm('¿Rechazar esta propuesta? La documentación aprobada se conserva.'))return;
        try{await api(`/api/v1/guide/proposals/${id}/reject`,{method:'POST'});target.classList.add('hidden');await loadLibrary();notify('Propuesta rechazada.');}catch(error){notify(error.message,true);}
      });actions.prepend(reject);
    }
  }catch(error){notify(error.message,true);}
}
$('propose-draft').addEventListener('click',async()=>{
  const button=$('propose-draft');if(button.disabled)return;button.disabled=true;
  try{
  if((!currentDraft||dirty)&&!await saveDraft())return;
  try{await api(`/api/v1/drafts/${currentDraft.id}/propose`,{method:'POST',body:JSON.stringify({revision:currentDraft.revision})});libraryMode='pending';showView('library');libraryTab('pending');notify('Borrador preparado. Revisa el contenido y apruébalo para incorporarlo.');}
  catch(error){notify(error.message,true);}
  }finally{button.disabled=false;}
});
$('import-file').addEventListener('click',async()=>{
  const file=$('source-file').files[0],button=$('import-file');
  if(!file){notify('Selecciona un archivo para importar.',true);return;}
  if(file.size>512000){notify('El archivo debe ser de hasta 512 KB.',true);return;}
  button.disabled=true;
  try{const content=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());const result=await api('/api/v1/guide/import-file',{method:'POST',body:JSON.stringify({filename:file.name,content,project:$('import-project').value.trim()||'General',area:$('import-area').value.trim()||'General'})});notify(result.created.length?'Archivo recibido. Está en Mi documentación → Por incorporar.':'El contenido ya estaba incorporado o pendiente de revisión.');loadGuideStatus();}
  catch(error){notify(error.message,true);}finally{button.disabled=false;}
});
$('import-package').addEventListener('click',async()=>{
  const file=$('package-file').files[0],button=$('import-package');
  if(!file){notify('Selecciona un paquete ZIP de Support AI.',true);return;}
  if(file.size>16000000){notify('El paquete debe ser de hasta 16 MB.',true);return;}
  button.disabled=true;button.textContent='Comprobando paquete…';
  try{const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));const result=await api('/api/v1/guide/import-package',{method:'POST',body:JSON.stringify({payload:btoa(binary)})});notify(`${result.created.length} cambios recibidos para revisar. No se sobrescribió la guía.`);loadGuideStatus();}
  catch(error){notify(error.message,true);}finally{button.disabled=false;button.textContent='Recibir cambios para revisión';}
});
