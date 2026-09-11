(async()=>{
await I18n.ready;
const {t,setText}=I18n;
const $ = id => document.getElementById(id);
let cachedKey='';try{cachedKey=sessionStorage.getItem('lan-share-key')||'';}catch{}
const key = location.hash.slice(1) || cachedKey;
if (key) { try { sessionStorage.setItem('lan-share-key', key); } catch {} }
let pc;
let sourceList=[];
function renderSources(){
  const selected=$('sources').value;$('sources').replaceChildren();
  for(const source of sourceList){const option=document.createElement('option');option.value=source.id;
    option.textContent=source.kind==='display'?`${t('Экран')} ${source.index} · ${source.width}×${source.height}`:`${source.app || t('Окно')} — ${source.title || t('Без названия')}`;
    $('sources').append(option);
  }
  if(sourceList.some(source=>source.id===selected))$('sources').value=selected;
}
$('language').onchange=event=>I18n.change(event.target.value);
window.addEventListener('languagechange',renderSources);
let isLocal=false, parentFolder="", fileSignature="";
function message(text) { setText($('status'), text); }
async function api(path, body) {
  const response = await fetch('/api/' + path, {method: body === undefined ? 'GET' : 'POST', headers: {'Authorization':'Bearer '+key, 'Content-Type':'application/json'}, body: body === undefined ? undefined : JSON.stringify(body)});
  if (!response.ok) {const text=await response.text(); let error=text;try{error=JSON.parse(text).error || text;}catch{}throw new Error(error);}
  return response.json();
}
function action(id, fn) { $(id).onclick = async () => {$(id).disabled=true;try{await fn();}catch(e){message(e.message);}finally{$(id).disabled=false;}}; }
function disconnect() { if(pc){pc.close();pc=null;} $('live').srcObject=null; }
async function refresh() {
  message(t('Запрашиваем список окон у macOS…'));
  const sources = await api('sources'); $('sources').replaceChildren();
  sourceList=sources;renderSources();
  message(t('Выберите окно или экран и начните трансляцию.'));
}
action('refresh', refresh);
action('start', async()=>{if(!$('sources').value)throw new Error(t('Сначала нажмите «Обновить окна» и выберите источник.'));message(t('Запускаем захват…'));await api('start',{source:$('sources').value});message(t('Трансляция готова. Откройте ссылку на iPhone и нажмите «Смотреть».'));});
action('stop', async()=>{await api('stop',{});disconnect();message(t('Трансляция остановлена.'));});
action('disconnect', async()=>{disconnect();message(t('Вы отключились.'));});
action('watch', async()=>{
  disconnect(); $('movie').pause(); message(t('Соединяемся…'));
  const connection = new RTCPeerConnection({iceServers:[]}); pc=connection;
  connection.addTransceiver('video',{direction:'recvonly'});
  connection.addTransceiver('audio',{direction:'recvonly'});
  const stream = new MediaStream();
  $('live').srcObject = stream;
  $('live').muted = location.hostname === 'localhost' || location.hostname === '127.0.0.1';
  connection.ontrack=event=>{stream.addTrack(event.track);$('live').play().catch(()=>message(t('Нажмите «Включить звук» или ▶ на видео.')));};
  connection.onconnectionstatechange=()=>{if(pc!==connection)return;message(({connected:t('Прямой эфир · звук приложения/системы'),failed:t('Не удалось подключиться. Проверьте Wi-Fi, VPN и брандмауэр, затем нажмите «Смотреть».'),disconnected:t('Связь прервалась. Нажмите «Смотреть», чтобы подключиться снова.'),closed:t('Соединение закрыто.')})[connection.connectionState] || t('Соединяемся…'));};
  try {
    await connection.setLocalDescription(await connection.createOffer());
    if(connection.iceGatheringState!=='complete') await new Promise((resolve,reject)=>{
      const timeout=setTimeout(()=>reject(new Error(t('Не удалось собрать сетевые адреса. Проверьте сеть.'))),12000);
      connection.onicegatheringstatechange=()=>{if(connection.iceGatheringState==='complete'){clearTimeout(timeout);resolve();}};
    });
    const answer=await api('offer',{sdp:connection.localDescription.sdp,buffer_ms:Number($('buffer').value)});
    await connection.setRemoteDescription(answer);
  } catch(e) {disconnect();throw e;}
});
action('sound',async()=>{$('live').muted=false;await $('live').play();message(t('Звук включён.'));});
action('fullscreen',async()=>{const v=$('live');if(v.webkitEnterFullscreen)v.webkitEnterFullscreen();else if(v.requestFullscreen)await v.requestFullscreen();});
async function refreshFiles() {
  const files=await api('files');
  const signature=JSON.stringify(files);
  if(signature===fileSignature)return;
  fileSignature=signature; delete $('files').dataset.i18n; $('files').replaceChildren();
  if(!files.length)setText($('files'), 'Пока нет файлов. На Mac нажмите «Выбрать файлы на Mac».');
  for(const file of files){
    const row=document.createElement('div'); row.className='media-row';
    const button=document.createElement('button');button.textContent='▶  '+file.name;
    button.onclick=()=>{disconnect();const v=$('movie');v.hidden=false;v.src='/media/'+encodeURIComponent(file.id)+'?key='+encodeURIComponent(key);v.play().catch(()=>message(t('Нажмите ▶. Если формат не поддерживается, преобразуйте файл в MP4 по инструкции.')));};
    row.append(button);
    if(isLocal){const remove=document.createElement('button');setText(remove, 'Убрать');remove.onclick=async()=>{try{await api('media/remove',{id:file.id});await refreshFiles();}catch(e){message(e.message);}};row.append(remove);}
    $('files').append(row);
  }
}
async function browseFolder(path) {
  const result=await api('media/browse',path?{path}:{});
  $('folder-path').value=result.path;parentFolder=result.parent;
  $('folder-entries').replaceChildren();delete $('picker-status').dataset.i18n;$('picker-status').textContent='';
  for(const entry of result.entries){
    if(entry.directory){const b=document.createElement('button');b.textContent='📁 '+entry.name;b.onclick=()=>browseFolder(entry.path).catch(e=>{setText($('picker-status'),e.message);});$('folder-entries').append(b);}
    else {const label=document.createElement('label');const input=document.createElement('input');input.type='checkbox';input.value=entry.path;label.append(input,document.createTextNode(entry.name));$('folder-entries').append(label);}
  }
  if(!result.entries.length)setText($('picker-status'), 'Нет медиафайлов или подпапок.');
}
action('choose-files',async()=>{$('picker').hidden=false;await browseFolder();});
action('folder-open',()=>browseFolder($('folder-path').value));
action('folder-up',()=>browseFolder(parentFolder));
action('close-picker',async()=>{$('picker').hidden=true;});
action('publish-files',async()=>{
  const paths=Array.from($('folder-entries').querySelectorAll('input:checked')).map(input=>input.value);
  if(!paths.length)throw new Error(t('Отметьте файлы для добавления.'));
  await api('media/add',{paths});await refreshFiles();$('picker').hidden=true;message(t('Файлы доступны на телефоне. Список обновится автоматически.'));
});
action('refresh-files',refreshFiles);
setInterval(()=>{if(!document.hidden)refreshFiles().catch(()=>{});},5000);
window.addEventListener('pagehide',disconnect);
(async()=>{
  try{
    const state=await api('status');$('admin').hidden=!state.local;isLocal=state.local;$('choose-files').hidden=!isLocal;
    message(state.source?t('Mac готов. Нажмите «Смотреть».'):t('На Mac пока не выбран источник.'));
    if(state.local){setText($('share'),'Ссылка для iPhone напечатана в Terminal. Доступ к просмотру есть у тех, кому вы её передадите.');}
    await refreshFiles();
    $('movie').onerror=()=>message(t('Safari не смог открыть формат файла. В инструкции есть команда преобразования в MP4.'));
  }catch(e){message(e.message);}
})();

})().catch(error=>{document.getElementById('status').textContent=error.message;});
