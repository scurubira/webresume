'use strict';
const $ = selector => document.querySelector(selector);
const $$ = selector => document.querySelectorAll(selector);
const storageKey = 'cvlink-builder-v1';

const emptyData = () => ({
  name: '', title: '', email: '', phone: '', location: '', summary: '',
  experience: [], education: [], skills: []
});

let data = emptyData();
let template = 'classic';

try {
  const saved = JSON.parse(localStorage.getItem(storageKey) || 'null');
  if (saved && typeof saved === 'object') data = { ...emptyData(), ...saved };
} catch {}

const normalizeArray = value => Array.isArray(value) ? value : [];

const fieldIds = {
  name: 'b-name', title: 'b-title', email: 'b-email', phone: 'b-phone', location: 'b-location', summary: 'b-summary'
};

function message(text, error = false) {
  const el = $('#builder-message');
  el.textContent = text;
  el.className = 'message ' + (error ? 'error' : 'success');
}

function persist() {
  try { localStorage.setItem(storageKey, JSON.stringify(data)); } catch {}
}

function loadForm() {
  for (const [key, id] of Object.entries(fieldIds)) {
    const el = $('#' + id);
    if (el) el.value = data[key] || '';
  }
  renderRepeater('experience', data.experience);
  renderRepeater('education', data.education);
  renderRepeater('skills', data.skills);
}

function updateDataFromForm() {
  for (const [key, id] of Object.entries(fieldIds)) {
    const el = $('#' + id);
    if (el) data[key] = el.value.trim();
  }
  data.experience = readRepeater('experience');
  data.education = readRepeater('education');
  data.skills = readRepeater('skills');
}

function createRepeaterItem(section, item = {}) {
  const div = document.createElement('div');
  div.className = 'repeater-item';
  div.dataset.section = section;
  if (section === 'experience') {
    div.innerHTML = `<div class="field-group columns-2"><input data-key="role" placeholder="Cargo" value="${esc(item.role || '')}"><input data-key="company" placeholder="Empresa" value="${esc(item.company || '')}"></div><div class="field-group columns-2"><input data-key="start" placeholder="Início" value="${esc(item.start || '')}"><input data-key="end" placeholder="Fim" value="${esc(item.end || '')}"></div><textarea data-key="description" rows="3" placeholder="Descreva suas atividades e conquistas">${esc(item.description || '')}</textarea><button type="button" class="text-button remove" data-remove>Remover</button>`;
  } else if (section === 'education') {
    div.innerHTML = `<div class="field-group columns-2"><input data-key="course" placeholder="Curso" value="${esc(item.course || '')}"><input data-key="institution" placeholder="Instituição" value="${esc(item.institution || '')}"></div><div class="field-group columns-2"><input data-key="start" placeholder="Início" value="${esc(item.start || '')}"><input data-key="end" placeholder="Fim" value="${esc(item.end || '')}"></div><button type="button" class="text-button remove" data-remove>Remover</button>`;
  } else if (section === 'skills') {
    div.innerHTML = `<input data-key="name" placeholder="Ex.: Inglês avançado, Python, Scrum" value="${esc(item.name || '')}"><button type="button" class="text-button remove" data-remove>Remover</button>`;
  }
  return div;
}

function renderRepeater(section, items) {
  const list = $('#' + section + '-list');
  list.innerHTML = '';
  for (const item of normalizeArray(items)) list.appendChild(createRepeaterItem(section, item));
}

function readRepeater(section) {
  const list = $('#' + section + '-list');
  return [...list.querySelectorAll('.repeater-item')].map(item => {
    const obj = {};
    item.querySelectorAll('[data-key]').forEach(el => obj[el.dataset.key] = el.value.trim());
    return obj;
  });
}

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
}

function nl2br(value) {
  return esc(value).replace(/\n/g, '<br>');
}

function renderPreview() {
  const p = $('#resume-preview');
  p.className = 'resume-sheet template-' + template;
  if (!data.name && !data.title && !data.summary && !normalizeArray(data.experience).length && !normalizeArray(data.education).length && !normalizeArray(data.skills).length) {
    p.innerHTML = `<div class="empty-preview"><span>◷</span><p>Preencha o editor para ver a prévia.</p></div>`;
    return;
  }

  const contact = [data.email, data.phone, data.location].filter(Boolean).join(' · ');
  const experience = normalizeArray(data.experience).filter(i => i.role || i.company || i.description);
  const education = normalizeArray(data.education).filter(i => i.course || i.institution);
  const skills = normalizeArray(data.skills).filter(i => i.name);

  const expHtml = experience.length ? `<section class="section-block"><h2>Experiência profissional</h2>${experience.map(i => `<div class="entry"><div class="entry-header"><div><strong>${esc(i.role || '')}</strong>${i.company ? `<span> — ${esc(i.company)}</span>` : ''}</div><span class="date">${esc([i.start, i.end].filter(Boolean).join(' – '))}</span></div><p>${nl2br(i.description || '')}</p></div>`).join('')}</section>` : '';
  const eduHtml = education.length ? `<section class="section-block"><h2>Formação</h2>${education.map(i => `<div class="entry"><div class="entry-header"><div><strong>${esc(i.course || '')}</strong>${i.institution ? `<span> — ${esc(i.institution)}</span>` : ''}</div><span class="date">${esc([i.start, i.end].filter(Boolean).join(' – '))}</span></div></div>`).join('')}</section>` : '';
  const skillsHtml = skills.length ? `<section class="section-block"><h2>Habilidades</h2><div class="skills-list">${skills.map(i => `<span class="skill-tag">${esc(i.name)}</span>`).join('')}</div></section>` : '';

  p.innerHTML = `<header class="resume-header"><h1>${esc(data.name || 'Seu nome')}</h1><p class="resume-title">${esc(data.title || '')}</p>${contact ? `<p class="resume-contact">${esc(contact)}</p>` : ''}</header>${data.summary ? `<section class="section-block"><h2>Resumo</h2><p>${nl2br(data.summary)}</p></section>` : ''}${expHtml}${eduHtml}${skillsHtml}`;
}

function schedulePreview() {
  updateDataFromForm();
  persist();
  renderPreview();
}

function addItem(section) {
  updateDataFromForm();
  data[section].push({});
  renderRepeater(section, data[section]);
  persist();
  renderPreview();
}

function removeItem(button) {
  const item = button.closest('.repeater-item');
  const section = item.dataset.section;
  item.remove();
  data[section] = readRepeater(section);
  persist();
  renderPreview();
}

function setTemplate(value) {
  template = value;
  renderPreview();
}

async function exportDocx() {
  updateDataFromForm();
  if (!data.name) return message('Preencha pelo menos o nome completo antes de exportar.', true);
  try {
    const response = await fetch('/api/export/docx', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ template, data })
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.error || 'Falha ao gerar DOCX.');
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'curriculo.docx';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    message('DOCX gerado com sucesso.');
  } catch (error) { message(error.message, true); }
}

function exportPdf() {
  updateDataFromForm();
  if (!data.name) return message('Preencha pelo menos o nome completo antes de exportar.', true);
  window.print();
}

function clearAll() {
  if (!confirm('Deseja limpar todos os dados do currículo?')) return;
  data = emptyData();
  persist();
  loadForm();
  renderPreview();
  message('Currículo limpo.');
}

function loadExample() {
  data = {
    name: 'Ana Silva', title: 'Designer de Produto', email: 'ana.silva@email.com', phone: '(11) 91234-5678', location: 'São Paulo, SP',
    summary: 'Designer de produto com mais de 6 anos de experiência criando experiências digitais centradas no usuário. Atuação em startups e empresas de tecnologia, liderando pesquisa, prototipação e handoff para desenvolvimento.',
    experience: [
      { role: 'Product Designer Sênior', company: 'TechNova', start: '2021', end: 'Atual', description: 'Lidero o design de novos produtos e melhorias de experiência para mais de 2 milhões de usuários.\nConduzo pesquisas qualitativas, workshops de ideação e protótipos de alta fidelidade.' },
      { role: 'UX Designer', company: 'Agência Croma', start: '2018', end: '2021', description: 'Desenvolvi interfaces para clientes de e-commerce, saúde e educação.\nColaborei com desenvolvedores e product managers em metodologias ágeis.' }
    ],
    education: [
      { course: 'Bacharelado em Design', institution: 'Universidade de São Paulo', start: '2013', end: '2017' }
    ],
    skills: [
      { name: 'Figma' }, { name: 'Adobe XD' }, { name: 'Design Systems' }, { name: 'Pesquisa com usuários' }, { name: 'HTML/CSS' }, { name: 'Inglês avançado' }
    ]
  };
  loadForm();
  renderPreview();
  persist();
  message('Exemplo carregado.');
}

$('#editor').addEventListener('input', schedulePreview);
$('#editor').addEventListener('change', schedulePreview);
$('#editor').addEventListener('click', event => {
  const add = event.target.closest('[data-add]');
  if (add) return addItem(add.dataset.add);
  const remove = event.target.closest('[data-remove]');
  if (remove) return removeItem(remove);
});
$('#template-select').addEventListener('change', event => setTemplate(event.target.value));
$('#export-pdf').addEventListener('click', exportPdf);
$('#export-docx').addEventListener('click', exportDocx);
$('#clear-builder').addEventListener('click', clearAll);
$('#load-example').addEventListener('click', loadExample);

loadForm();
setTemplate(template);
