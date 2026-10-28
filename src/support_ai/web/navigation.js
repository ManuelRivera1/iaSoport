'use strict';
let restoringNavigation=false,displayedNavigation=null,revertingNavigation=false;
const moduleViews=['chat','editor','incident','library','sharing','admin'];
function activeModule(){return document.querySelector('.view:not(.hidden)')?.id.replace('view-','')||'chat';}
function navigationState(view=activeModule()){
  const state={view};
  if(view==='chat')state.landing=!$('chat-welcome').classList.contains('hidden');
  if(view==='library'){state.mode=libraryMode;state.folders=[...folderPath];state.document=libraryMode==='official'?openDocumentPath:null;state.editing=libraryMode==='official'&&libraryEditorOpen;state.proposal=['pending','deletions'].includes(libraryMode)&&!$('library-detail').classList.contains('hidden')?selectedProposal:null;}
  if(view==='editor'){state.step=step;state.draft=currentDraft?.id||null;}
  if(view==='incident'){state.draft=incidentDraft?.id||null;state.review=!$('incident-review').classList.contains('hidden');}
  if(view==='admin')state.category=$('catalog-category').value;
  return state;
}
function updateNavigationButtons(){
  $('navigation-back').disabled=!(history.state?.supportAi&&history.state.depth>0);
}
function recordNavigation(view=activeModule()){
  if(restoringNavigation)return;
  const state=navigationState(view),previous=history.state;
  if(previous?.supportAi&&JSON.stringify(previous.page)===JSON.stringify(state)){displayedNavigation=previous;updateNavigationButtons();return;}
  const next={supportAi:true,depth:previous?.supportAi?previous.depth+1:0,page:state};
  history.pushState(next,'','#'+view);displayedNavigation=next;updateNavigationButtons();
}
function confirmEditorExit(){
  if(activeModule()==='admin'&&catalogDirty){
    if(!confirm('Hay cambios del catálogo sin guardar. ¿Descartarlos y salir?'))return false;
    catalogDirty=false;
  }
  if(activeModule()==='library'&&libraryEditorDirty){
    if(!confirm('Hay cambios del documento sin guardar. ¿Descartarlos y volver?'))return false;
    libraryEditorDirty=false;
  }
  return true;
}
function navigateModule(view){
  if(!confirmEditorExit())return;
  if(view==='editor'){startNewDocument();return;}
  if(view==='incident'){startNewIncident();return;}
  if(view==='chat')chatHome();
  if(view==='library'){libraryMode='official';folderMode='official';folderPath=[];openDocumentPath=null;selectedProposal=null;$('library-search').value='';$('project-filter').value='';}
  if(view==='sharing')['import-project','import-area','source-file','package-file'].forEach(id=>$(id).value='');
  if(view==='admin'){
    if(catalogDirty&&!confirm('Hay cambios del catálogo sin guardar. ¿Descartarlos y volver al inicio?'))return;
    $('catalog-category').value='projects';$('catalog-search').value='';$('catalog-status').value='all';resetCatalog();renderCatalog();
  }
  showView(view);
}
async function restoreNavigation(state){
  restoringNavigation=true;
  try{
    const page=state.page,view=moduleViews.includes(page?.view)?page.view:'chat';
    if(view==='library'){libraryMode=page.mode||'official';folderMode=libraryMode;folderPath=Array.isArray(page.folders)?page.folders:[];openDocumentPath=null;selectedProposal=null;$('library-search').value='';$('project-filter').value='';}
    showView(view,false);
    if(view==='chat'){
      if(page.landing||!$('messages').children.length)chatHome();
      else{$('chat-welcome').classList.add('hidden');$('messages').classList.remove('hidden');$('chat-return').classList.remove('hidden');}
    }
    if(view==='library'){
      await loadLibrary();libraryTab(libraryMode);
      if(page.document){const item=official.find(item=>item.path===page.document);if(item){openLibraryDocument(item);if(page.editing)editLibraryDocument(item);}}
      if(page.proposal)await openProposal(page.proposal);
    }
    if(view==='editor'){
      if(page.draft&&currentDraft?.id!==page.draft){currentDraft=await api('/api/v1/drafts/'+page.draft);setData(currentDraft.data);dirty=false;$('draft-state').textContent='Borrador guardado';}
      setStep(page.step||1);
    }
    if(view==='incident'){
      if(page.draft&&incidentDraft?.id!==page.draft)openIncidentDraft(await api('/api/v1/drafts/'+page.draft));
      incidentReview(Boolean(page.review&&incidentDraft));
    }
    if(view==='admin'){await loadAdmin();$('catalog-category').value=page.category||'projects';resetCatalog();renderCatalog();}
  }catch(error){notify('No se pudo recuperar esa pantalla: '+error.message,true);}
  finally{restoringNavigation=false;displayedNavigation=state;updateNavigationButtons();}
}
window.addEventListener('popstate',event=>{
  if(revertingNavigation){revertingNavigation=false;updateNavigationButtons();return;}
  if(!event.state?.supportAi)return;
  if(!confirmEditorExit()){
    const delta=(displayedNavigation?.depth||0)-event.state.depth;
    if(delta){revertingNavigation=true;history.go(delta);}return;
  }
  restoreNavigation(event.state);
});
$('navigation-back').addEventListener('click',()=>history.back());
$('navigation-home').addEventListener('click',()=>navigateModule(activeModule()));
const initial=history.state?.supportAi?history.state:null;
if(initial)restoreNavigation(initial);
else{
  const requested=location.hash.slice(1),view=moduleViews.includes(requested)?requested:'chat';
  const state={supportAi:true,depth:0,page:{view,...(view==='chat'?{landing:true}:{})}};
  history.replaceState(state,'','#'+view);displayedNavigation=state;
  if(view!=='chat')restoreNavigation(state);else updateNavigationButtons();
}
