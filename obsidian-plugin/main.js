'use strict';
/*
 * Manifexa — a personal Obsidian plugin (note generator).
 *
 * "Add paper by DOI" fetches a work from OpenAlex and writes a fully-filled
 * note: title, authors, year, venue, topics, and the abstract — plus stub
 * notes for each author and topic so the [[wikilinks]] resolve and the
 * manifexa engine can curate the graph from them. "Suggest related" asks your
 * local LLM (balthar via Ollama) for adjacent work. Self-contained: it talks
 * only to OpenAlex and your localhost balthar tunnel, and writes plain files.
 */
const { Plugin, Modal, Notice, Setting, PluginSettingTab, requestUrl, normalizePath } = require('obsidian');

const DEFAULTS = {
  paperFolder: 'paper',
  personFolder: 'person',
  topicFolder: 'topic',
  mailto: '',
  baltharUrl: 'http://localhost:11435',
  baltharModel: 'qwen3-coder-next:q8_0',
};

// slugify a title the same way manifexa does, so ids line up with the engine.
function slug(s) {
  return (s || '')
    .toLowerCase()
    .normalize('NFKD').replace(/[\u0300-\u036f]/g, '')   // strip accents
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80) || 'untitled';
}

// OpenAlex stores abstracts as {word: [positions]} — put them back in order.
function reconstructAbstract(inv) {
  if (!inv) return '';
  const placed = [];
  for (const [word, positions] of Object.entries(inv)) {
    for (const p of positions) placed.push([p, word]);
  }
  placed.sort((a, b) => a[0] - b[0]);
  return placed.map((x) => x[1]).join(' ');
}

function yamlLinkList(names) {
  // quoted so YAML doesn't read the leading [[ as a flow sequence.
  return names.map((n) => `\n  - "[[${n}]]"`).join('');
}

module.exports = class ManifexaPlugin extends Plugin {
  async onload() {
    this.settings = Object.assign({}, DEFAULTS, await this.loadData());
    this.addCommand({
      id: 'manifexa-add-paper',
      name: 'Add paper by DOI',
      callback: () => new DoiModal(this.app, (v) => this.addPaper(v)).open(),
    });
    this.addCommand({
      id: 'manifexa-suggest-related',
      name: 'Suggest related (via balthar)',
      callback: () => this.suggestRelated(),
    });
    this.addRibbonIcon('graph', 'Manifexa: add paper', () =>
      new DoiModal(this.app, (v) => this.addPaper(v)).open());
    this.addSettingTab(new ManifexaSettingTab(this.app, this));
  }

  async saveSettings() { await this.saveData(this.settings); }

  async fetchWork(input) {
    let q = (input || '').trim().replace(/^doi:/i, '');
    if (!/^https?:\/\//i.test(q) && !/^W\d+$/i.test(q)) q = 'https://doi.org/' + q;
    let url = 'https://api.openalex.org/works/' + q;
    if (this.settings.mailto) url += '?mailto=' + encodeURIComponent(this.settings.mailto);
    const res = await requestUrl({ url, headers: { 'User-Agent': 'manifexa-obsidian/0.1' } });
    if (res.status >= 400) throw new Error('OpenAlex HTTP ' + res.status);
    return res.json;
  }

  // create a note, making the folder if needed; never clobber an existing note.
  async writeNote(folder, name, content) {
    const dir = normalizePath(folder);
    if (!(await this.app.vault.adapter.exists(dir))) {
      await this.app.vault.createFolder(dir).catch(() => {});
    }
    const path = normalizePath(folder + '/' + name + '.md');
    if (await this.app.vault.adapter.exists(path)) return path;
    await this.app.vault.create(path, content);
    return path;
  }

  async addPaper(input) {
    if (!input) return;
    new Notice('Manifexa: fetching…');
    let work;
    try {
      work = await this.fetchWork(input);
    } catch (e) {
      new Notice('Manifexa: could not fetch — ' + e.message);
      return;
    }

    const title = work.title || work.display_name || 'Untitled';
    const authors = (work.authorships || []).map((a) => (a.author || {}).display_name).filter(Boolean);
    const topics = (work.topics || []).slice(0, 4).map((t) => t.display_name).filter(Boolean);
    const venue = ((work.primary_location || {}).source || {}).display_name || '';
    const abstract = reconstructAbstract(work.abstract_inverted_index);
    const doi = work.doi || '';
    const oa = (work.id || '').replace('https://openalex.org/', '');

    const lines = ['---', 'type: paper', 'title: ' + JSON.stringify(title)];
    if (work.publication_year) lines.push('year: ' + work.publication_year);
    if (doi) lines.push('doi: ' + doi);
    if (venue) lines.push('venue: ' + JSON.stringify(venue));
    if (oa) lines.push('openalex: ' + oa);
    lines.push('status: curated');
    if (authors.length) lines.push('authors:' + yamlLinkList(authors));
    if (topics.length) lines.push('topics:' + yamlLinkList(topics));
    lines.push('---', '');
    const body = abstract ? '## Abstract\n\n' + abstract + '\n' : '';
    const paperPath = await this.writeNote(this.settings.paperFolder, slug(title), lines.join('\n') + body);

    // stub notes so the [[wikilinks]] resolve in Obsidian + the engine graphs them.
    for (const n of authors) {
      await this.writeNote(this.settings.personFolder, slug(n),
        '---\ntype: person\ntitle: ' + JSON.stringify(n) + '\naliases: [' + JSON.stringify(n) + ']\nstatus: candidate\n---\n');
    }
    for (const n of topics) {
      await this.writeNote(this.settings.topicFolder, slug(n),
        '---\ntype: topic\ntitle: ' + JSON.stringify(n) + '\naliases: [' + JSON.stringify(n) + ']\nstatus: candidate\n---\n');
    }

    new Notice('Manifexa: added “' + title + '” · ' + authors.length + ' authors · ' + topics.length + ' topics');
    const file = this.app.vault.getAbstractFileByPath(paperPath);
    if (file) this.app.workspace.getLeaf(false).openFile(file);
  }

  async suggestRelated() {
    const file = this.app.workspace.getActiveFile();
    if (!file) { new Notice('Manifexa: open a note first'); return; }
    const fm = (this.app.metadataCache.getFileCache(file) || {}).frontmatter || {};
    const title = fm.title || file.basename;
    new Notice('Manifexa: asking balthar…');
    try {
      const res = await requestUrl({
        url: this.settings.baltharUrl.replace(/\/$/, '') + '/api/generate',
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: this.settings.baltharModel,
          stream: false,
          prompt: 'List 3-5 research topics or well-known papers closely related to "' + title +
            '". Only real, well-established items. One per line, no commentary.',
        }),
      });
      const text = (res.json && res.json.response) || res.text || '(no response)';
      new SuggestModal(this.app, title, text.trim()).open();
    } catch (e) {
      new Notice('Manifexa: balthar unreachable — is the tunnel up? ' + e.message);
    }
  }
};

class DoiModal extends Modal {
  constructor(app, onSubmit) { super(app); this.onSubmit = onSubmit; }
  onOpen() {
    const { contentEl } = this;
    contentEl.createEl('h3', { text: 'Manifexa · add paper' });
    const input = contentEl.createEl('input', {
      attr: { type: 'text', placeholder: 'DOI, arXiv/DOI URL, or OpenAlex id', style: 'width:100%' },
    });
    input.focus();
    const submit = () => { const v = input.value.trim(); this.close(); if (v) this.onSubmit(v); };
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
    const btn = contentEl.createEl('button', { text: 'Add', attr: { style: 'margin-top:10px' } });
    btn.addEventListener('click', submit);
  }
  onClose() { this.contentEl.empty(); }
}

class SuggestModal extends Modal {
  constructor(app, title, text) { super(app); this.titleText = title; this.text = text; }
  onOpen() {
    const { contentEl } = this;
    contentEl.createEl('h3', { text: 'Related to: ' + this.titleText });
    contentEl.createEl('pre', { text: this.text, attr: { style: 'white-space:pre-wrap' } });
  }
  onClose() { this.contentEl.empty(); }
}

class ManifexaSettingTab extends PluginSettingTab {
  constructor(app, plugin) { super(app, plugin); this.plugin = plugin; }
  display() {
    const { containerEl } = this;
    containerEl.empty();
    const s = this.plugin.settings;
    const row = (name, desc, key, ph) => new Setting(containerEl).setName(name).setDesc(desc)
      .addText((t) => t.setPlaceholder(ph || '').setValue(s[key])
        .onChange(async (v) => { s[key] = v.trim(); await this.plugin.saveSettings(); }));
    row('Papers folder', 'Where paper notes are written', 'paperFolder', 'paper');
    row('People folder', 'Where author notes are written', 'personFolder', 'person');
    row('Topics folder', 'Where topic notes are written', 'topicFolder', 'topic');
    row('OpenAlex mailto', 'Optional email for OpenAlex\'s polite pool', 'mailto', 'you@example.com');
    row('balthar URL', 'Local Ollama endpoint (your SSH tunnel)', 'baltharUrl', 'http://localhost:11435');
    row('balthar model', 'Ollama model name', 'baltharModel', 'qwen3-coder-next:q8_0');
  }
}
