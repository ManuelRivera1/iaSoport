'use strict';
let incidentDraft=null,incidentDirty=false;
const incidentFields={project:'incident-project',service:'incident-service',area:'incident-area',owner:'incident-owner',name:'incident-name',error_code:'incident-code',incident_status:'incident-status',incident_environment:'incident-environment',incident_symptoms:'incident-symptoms',incident_cause:'incident-cause',incident_solution:'incident-solution',incident_verification:'incident-verification'};
function incidentData(){
  const data=incidentDraft?{...incidentDraft.data}:{};
  Object.entries(incidentFields).forEach(([key,id])=>data[key]=$(id).value.trim());
  return {...data,kind:'incident',is_new_error:true};
}
function incidentServices(current=$('incident-service').value){
  const parent=catalogEntries.find(entry=>entry.category==='projects'&&entry.active&&entry.name===$('incident-project').value);
  fillSelect($('incident-service'),catalogEntries.filter(entry=>entry.category==='services'&&entry.active&&entry.project_id===parent?.id),current,'Servicio por identificar');
}
function populateIncidentCatalog(){
  for(const [field,category] of Object.entries({project:'projects',area:'areas',owner:'teams'})){
    const control=$(incidentFields[field]),current=control.value||(field==='project'?'General':'');
    fillSelect(control,catalogEntries.filter(entry=>entry.category===category&&entry.active),current,'Seleccionar…');
  }
  incidentServices();
}
function incidentReview(show){
  $('incident-fields').classList.toggle('hidden',show);$('incident-review').classList.toggle('hidden',!show);$('incident-check').classList.toggle('hidden',show);
  if(typeof recordNavigation==='function'&&!$('view-incident').classList.contains('hidden'))recordNavigation('incident');
}
function openIncidentDraft(draft){
  if(incidentDirty&&!confirm('¿Dejar los cambios sin guardar y abrir este borrador de error?'))return;
  incidentDraft=draft;populateIncidentCatalog();
  for(const [key,id] of Object.entries(incidentFields)){
    const control=$(id),value=draft.data[key]||(key==='incident_status'?'investigating':key==='incident_symptoms'?draft.data.errors||'':key==='incident_solution'?draft.data.procedures||'':'');
    if(control.tagName==='SELECT'&&value&&![...control.options].some(option=>option.value===value)){const option=node('option',value+' (actual)');option.value=value;control.append(option);}control.value=value;
  }
  incidentServices(draft.data.service);incidentDirty=false;incidentReview(false);$('incident-state').textContent='Borrador guardado';showView('incident');
}
$('incident-project').addEventListener('change',()=>incidentServices(''));
$('incident-status').addEventListener('change',()=>{
  if($('incident-status').value==='resolved')$('incident-diagnosis').open=true;
});
$('incident-form').addEventListener('input',()=>{incidentDirty=true;$('incident-state').textContent='Cambios sin guardar';});
async function saveIncident(){
  const data=incidentData();
  if(!data.area||!data.name){incidentReview(false);notify('Completa el área y el título del error para guardar.',true);$(data.area?'incident-name':'incident-area').focus();return false;}
  const button=$('incident-save');button.disabled=true;
  try{incidentDraft=await api(incidentDraft?'/api/v1/drafts/'+incidentDraft.id:'/api/v1/drafts',{method:incidentDraft?'PUT':'POST',body:JSON.stringify(incidentDraft?{revision:incidentDraft.revision,data}:data)});incidentDirty=false;$('incident-state').textContent='Borrador guardado';return true;}
  catch(error){notify(error.message,true);return false;}finally{button.disabled=false;}
}
$('incident-form').addEventListener('submit',async event=>{event.preventDefault();if(await saveIncident())notify('Borrador del error guardado. Puedes continuar después desde Mis borradores.');});
$('incident-check').addEventListener('click',async()=>{
  const data=incidentData();
  if(!data.incident_symptoms){notify('Describe los síntomas y cuándo ocurre el error.',true);$('incident-symptoms').focus();return;}
  if(data.incident_status==='resolved'&&!data.incident_solution){$('incident-diagnosis').open=true;notify('Para marcarlo como resuelto, describe la solución aplicada.',true);$('incident-solution').focus();return;}
  if(await saveIncident()){renderMarkdown(incidentDraft.markdown,$('incident-preview'));incidentReview(true);$('view-incident').scrollIntoView({behavior:'smooth',block:'start'});}
});
$('incident-back').addEventListener('click',()=>incidentReview(false));
$('incident-propose').addEventListener('click',async()=>{
  const button=$('incident-propose');if(button.disabled||!incidentDraft)return;button.disabled=true;
  try{await api('/api/v1/drafts/'+incidentDraft.id+'/propose',{method:'POST',body:JSON.stringify({revision:incidentDraft.revision})});$('library-search').value='';libraryMode='pending';showView('library');libraryTab('pending');notify('Error preparado para incorporarlo a tu guía local.');}
  catch(error){notify(error.message,true);}finally{button.disabled=false;}
});
function startNewIncident(){
  if(incidentDirty&&!confirm('¿Descartar los cambios sin guardar y empezar otro registro?'))return;
  incidentDraft=null;incidentDirty=false;Object.entries(incidentFields).forEach(([key,id])=>$(id).value=key==='incident_status'?'investigating':'');populateIncidentCatalog();incidentReview(false);$('incident-state').textContent='Nuevo borrador';$('incident-diagnosis').open=false;showView('incident');return true;
}
$('incident-new').addEventListener('click',startNewIncident);
populateIncidentCatalog();
