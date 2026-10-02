'use strict';
const $ = selector => document.querySelector(selector);
const storageKey = 'cvlink-owners-v1';
let owners = [];
let config = { email_available: false };
let polling = false;
let file = null;
try { owners = JSON.parse(localStorage.getItem(storageKey) || '[]'); if (!Array.isArray(owners)) owners = []; owners = owners.filter(item => item && /^[A-Za-z0-9_-]{8}$/.test(item.slug) && typeof item.owner_token === 'string'); } catch { owners = []; }
const seen = new Map();
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
function message(selector, text, error = false) { const element = $(selector); element.textContent = text; element.className = 'message ' + (error ? 'error' : 'success'); }
function persist() { try { localStorage.setItem(storageKey, JSON.stringify(owners)); } catch { message('#dashboard-message', 'Não foi possível salvar as chaves neste navegador. Guarde a chave privada exibida abaixo para recuperar o painel.', true); } }
async function api(path, options = {}) { const response = await fetch(path, options); let data; try { data = await response.json(); } catch { throw new Error('O backend não está disponível. Abra o site pelo servidor Python (server.py), não pelo arquivo HTML ou pelo servidor estático.'); } if (!response.ok) throw new Error(data.error || 'Não foi possível completar a solicitação.'); return data; }
function chooseFile(candidate) { if (!candidate) return; if (!candidate.name.toLowerCase().endsWith('.pdf') || candidate.size > 10 * 1024 * 1024 || candidate.size === 0) { file = null; $('#cv-file').value = ''; $('#file-label').textContent = 'Arraste seu currículo para cá'; message('#upload-message', 'Escolha um PDF de até 10 MB.', true); return; } file = candidate; $('#file-label').textContent = `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB`; if (!$('#cv-name').value) $('#cv-name').value = candidate.name.replace(/\.pdf$/i, '').slice(0, 120); message('#upload-message', 'Arquivo pronto para envio.'); }
$('#cv-file').addEventListener('change', event => chooseFile(event.target.files[0]));
const zone = $('#dropzone');
for (const type of ['dragenter', 'dragover']) zone.addEventListener(type, event => { event.preventDefault(); zone.classList.add('dragging'); });
for (const type of ['dragleave', 'drop']) zone.addEventListener(type, event => { event.preventDefault(); zone.classList.remove('dragging'); });
zone.addEventListener('drop', event => { const files = event.dataTransfer.files; if (files.length) { $('#cv-file').files = files; chooseFile(files[0]); } });
$('#upload-form').addEventListener('submit', async event => {
  event.preventDefault(); if (!file) return message('#upload-message', 'Escolha seu arquivo PDF.', true);
  $('#submit-upload').disabled = true; $('#upload-progress').hidden = false; message('#upload-message', 'Enviando seu currículo…');
  try {
    const result = await new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest(); xhr.open('POST', '/api/cvs'); xhr.timeout = 60000;
      xhr.setRequestHeader('Content-Type', 'application/pdf'); xhr.setRequestHeader('X-CV-Name', encodeURIComponent($('#cv-name').value)); xhr.setRequestHeader('X-Owner-Email', encodeURIComponent($('#owner-email').value));
      xhr.upload.onprogress = event => { if (event.lengthComputable) $('#upload-progress').value = event.loaded / event.total * 100; };
      xhr.onload = () => { try { const data = JSON.parse(xhr.responseText); if (xhr.status >= 400) reject(new Error(data.error)); else resolve(data); } catch { reject(new Error('O upload precisa do backend. Inicie python3 server.py e abra o endereço informado.')); } };
      xhr.onerror = () => reject(new Error('Falha de conexão. Verifique se o servidor está ativo.')); xhr.ontimeout = () => reject(new Error('O envio demorou demais. Tente novamente.')); xhr.send(file);
    });
    owners.unshift({ slug: result.slug, owner_token: result.owner_token }); persist();
    message('#upload-message', result.email_enabled ? 'Link criado! As notificações por e-mail estão ativadas.' : 'Link criado. O envio de e-mail está indisponível até configurar o SMTP. Os acessos serão registrados no painel.');
    await refresh(); $('#dashboard').scrollIntoView({ behavior: 'smooth' }); $('#upload-form').reset(); file = null; $('#file-label').textContent = 'Arraste seu currículo para cá';
  } catch (error) { message('#upload-message', error.message, true); }
  finally { $('#submit-upload').disabled = false; $('#upload-progress').hidden = true; }
});
function notify(name) { const toast = document.createElement('div'); toast.className = 'toast'; toast.setAttribute('role', 'status'); toast.textContent = `Novo acesso: ${name}`; document.body.append(toast); setTimeout(() => toast.remove(), 7000); if ('Notification' in window && Notification.permission === 'granted') new Notification('Seu currículo foi acessado', { body: name }); }
function card(owner, data) {
  const statuses = { sent: 'E-mail enviado', pending: 'E-mail na fila', failed: 'Falha no envio do e-mail', disabled: 'E-mail não configurado' };
  return `<article class="cv-card"><div class="cv-card-heading"><h3>${escapeHtml(data.name)}</h3><span class="view-count"><b>${data.count}</b> acessos</span></div><div class="share-row"><input aria-label="Link curto do currículo" readonly value="${escapeHtml(data.short_url)}"><button class="button small" data-copy="${escapeHtml(data.short_url)}">Copiar link ↗</button></div><p class="card-note">${data.email_enabled ? '✓ Notificações por e-mail ativadas' : 'E-mail indisponível: configure o SMTP e informe seu e-mail no upload.'} · Painel atualizado a cada 5 segundos.</p><details><summary>Guardar chave privada do painel</summary><p class="card-note">Guarde o link e esta chave para abrir seu painel em outro navegador. Compartilhe apenas o link público com recrutadores.</p><div class="owner-secret">${escapeHtml(owner.owner_token)}</div><button class="text-button" data-copy="${escapeHtml(owner.owner_token)}">Copiar chave privada</button></details><div class="event-title">HISTÓRICO DE ACESSOS</div>${data.events.length ? `<ul class="event-list">${data.events.map(item => `<li><span>↗ PDF acessado · ${escapeHtml(new Date(item.visited * 1000).toLocaleString('pt-BR'))}</span><small>${escapeHtml(statuses[item.mail_status] || item.mail_status)}</small></li>`).join('')}</ul>` : '<p class="card-note">Nenhum acesso ainda. Compartilhe seu link para começar.</p>'}</article>`;
}
async function refresh() {
  if (polling || !owners.length) return; polling = true;
  try {
    const results = await Promise.all(owners.map(async owner => { try { const data = await api(`/api/cvs/${owner.slug}`, { headers: { Authorization: 'Bearer ' + owner.owner_token } }); const previous = seen.get(owner.slug); if (previous !== undefined && data.count > previous) notify(data.name); seen.set(owner.slug, data.count); return card(owner, data); } catch (error) { return `<article class="cv-card"><p class="message error">${escapeHtml(error.message)}</p><p class="card-note">Código: ${escapeHtml(owner.slug)}</p></article>`; } }));
    // Preserve an open key section across polling updates.
    const openDetails = [...document.querySelectorAll('.cv-card details')].map(item => item.open);
    const active = document.activeElement;
    if (active && active.closest('.cv-card') && active.tagName === 'INPUT') return;
    $('#cv-list').innerHTML = results.join(''); document.querySelectorAll('.cv-card details').forEach((item, index) => { item.open = Boolean(openDetails[index]); });
  } finally { polling = false; }
}
$('#cv-list').addEventListener('click', async event => { const button = event.target.closest('[data-copy]'); if (!button) return; try { await navigator.clipboard.writeText(button.dataset.copy); const text = button.textContent; button.textContent = 'Copiado ✓'; setTimeout(() => { button.textContent = text; }, 2000); } catch { message('#dashboard-message', 'Selecione e copie o texto manualmente. O navegador não permitiu acesso à área de transferência.', true); } });
$('#enable-notifications').addEventListener('click', async () => { if (!('Notification' in window)) return message('#dashboard-message', 'Este navegador não oferece notificações do sistema.', true); try { const permission = await Notification.requestPermission(); message('#dashboard-message', permission === 'granted' ? 'Avisos ativados enquanto esta página estiver aberta. O e-mail funciona independentemente do painel.' : 'Permissão não concedida. O histórico continua disponível no painel.', permission !== 'granted'); } catch { message('#dashboard-message', 'Notificações do navegador indisponíveis. Use o painel.', true); } });
$('#restore-form').addEventListener('submit', async event => { event.preventDefault(); const slug = $('#restore-slug').value.trim().replace(/\/$/, '').split('/').pop(); const token = $('#restore-token').value.trim(); if (!/^[A-Za-z0-9_-]{8}$/.test(slug)) return message('#restore-message', 'Link ou código inválido.', true); try { await api(`/api/cvs/${slug}`, { headers: { Authorization: 'Bearer ' + token } }); owners = owners.filter(item => item.slug !== slug); owners.unshift({ slug, owner_token: token }); persist(); await refresh(); $('#restore-form').reset(); message('#restore-message', 'Painel recuperado.'); } catch (error) { message('#restore-message', error.message, true); } });
async function init() { try { config = await api('/api/config'); $('#email-help').textContent = config.email_available ? 'Você receberá um e-mail quando o PDF for acessado.' : 'Envio de e-mail pendente de configuração SMTP no servidor.'; $('#owner-email').required = config.email_available; await refresh(); } catch (error) { $('#email-help').textContent = 'Servidor indisponível.'; message('#upload-message', error.message, true); } }
init(); setInterval(refresh, 5000);
