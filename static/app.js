const state = {
  dataset: null,
  result: null,
  excluded: new Set(),
  activeTopic: 1,
  topicAlgorithm: "lda",
  selectedK: null,
  mapYear: null,
};
const colors = ["#1bbbd0", "#2866ff", "#b8e64e", "#ff9a48", "#7967e8", "#ef5b73", "#29a879", "#e3b341"];
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const esc = value => String(value ?? "").replace(/[&<>"']/g, char => (
  {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[char]
));
const fmt = (value, digits = 2) => Number(value).toLocaleString("it-IT", { maximumFractionDigits: digits });
const statCard = (label, value, suffix = "") => `<div class="stat-card"><small>${label}</small><strong>${value} <span>${suffix}</span></strong></div>`;
const activeLdaModel = () => state.result?.lda_models?.find(
  model => model.topics_count === state.selectedK
) || null;
const activeTopics = () => activeLdaModel()?.topics || state.result?.topics || [];
const activeYears = () => activeLdaModel()?.years || state.result?.years || [];
const activeAssignments = () => Object.fromEntries(
  (activeLdaModel()?.document_assignments || state.result?.documents || [])
    .map(document => [document.id, document])
);

function toast(message) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.remove("hidden");
  setTimeout(() => element.classList.add("hidden"), 4000);
}

function navigate(view) {
  if (view === "review" && !state.dataset) return toast("Prima importa un dataset.");
  if (view === "results" && !state.result) return toast("Prima esegui l'analisi.");
  $$(".view").forEach(element => element.classList.toggle("active", element.id === `view-${view}`));
  $$(".nav-item").forEach(element => element.classList.toggle("active", element.dataset.go === view));
  $("#page-title").textContent = ({ import: "Nuova analisi", review: "Corpus", results: "Risultati" })[view];
  $(".sidebar").classList.remove("open");
  window.scrollTo({ top: 0 });
}

$$("[data-go]").forEach(button => button.addEventListener("click", () => navigate(button.dataset.go)));
$(".mobile-menu").addEventListener("click", () => $(".sidebar").classList.toggle("open"));

const dropZone = $("#drop-zone");
["dragenter", "dragover"].forEach(name => dropZone.addEventListener(name, event => {
  event.preventDefault();
  dropZone.classList.add("dragging");
}));
["dragleave", "drop"].forEach(name => dropZone.addEventListener(name, event => {
  event.preventDefault();
  dropZone.classList.remove("dragging");
}));
dropZone.addEventListener("drop", event => uploadFile(event.dataTransfer.files[0]));
$("#file-input").addEventListener("change", event => uploadFile(event.target.files[0]));

async function uploadFile(file) {
  if (!file) return;
  const status = $("#upload-status");
  status.classList.remove("hidden");
  status.textContent = `Lettura di ${file.name}…`;
  const body = new FormData();
  body.append("file", file);
  try {
    const response = await fetch("/api/datasets", { method: "POST", body });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Importazione non riuscita");
    state.dataset = payload;
    state.excluded.clear();
    status.textContent = `${payload.summary.unique} documenti unici pronti.`;
    renderReview();
    setTimeout(() => navigate("review"), 300);
  } catch (error) {
    status.textContent = error.message;
    status.style.color = "#a72532";
    status.style.background = "#fff1f2";
  }
}

function renderReview() {
  const summary = state.dataset.summary;
  $("#dataset-stats").innerHTML = [
    ["Importati", summary.imported, "righe"],
    ["Unici", summary.unique, "paper"],
    ["Duplicati rimossi", summary.duplicates_removed, "automatici"],
    ["Abstract disponibili", summary.abstracts_available, "documenti"],
  ].map(([label, value, suffix]) => statCard(label, fmt(value, 0), suffix)).join("");
  $("#year-filter").innerHTML = `<option value="">Tutti gli anni</option>` +
    state.dataset.years.map(year => `<option>${year}</option>`).join("");
  renderPaperTable();
}

function renderPaperTable() {
  const query = $("#paper-search").value.toLowerCase();
  const year = $("#year-filter").value;
  const papers = state.dataset.papers.filter(paper => {
    const haystack = `${paper.title} ${paper.authors} ${paper.source}`.toLowerCase();
    return (!query || haystack.includes(query)) && (!year || String(paper.year) === year);
  });
  $("#paper-table-body").innerHTML = papers.slice(0, 500).map(paper => `
    <tr>
      <td><input class="paper-toggle" type="checkbox" data-paper="${paper.id}" ${state.excluded.has(paper.id) ? "" : "checked"} aria-label="Includi ${esc(paper.title)}"></td>
      <td><span class="paper-title">${esc(paper.title)}</span><span class="paper-meta">${esc(paper.authors || paper.source || "Autori non disponibili")}</span></td>
      <td>${paper.year || "—"}</td><td>${paper.citations}</td>
    </tr>`).join("");
  $$(".paper-toggle").forEach(input => input.addEventListener("change", () => {
    input.checked ? state.excluded.delete(input.dataset.paper) : state.excluded.add(input.dataset.paper);
    updateSelectedCount();
  }));
  updateSelectedCount();
}

$("#paper-search").addEventListener("input", renderPaperTable);
$("#year-filter").addEventListener("change", renderPaperTable);
function updateSelectedCount() {
  $("#selected-count").textContent = `${state.dataset.papers.length - state.excluded.size} selezionati`;
}

$("#start-analysis").addEventListener("click", runAnalysis);
async function runAnalysis() {
  const counts = [...new Set($("#topic-counts").value.split(/[,;\s]+/).map(Number)
    .filter(value => Number.isInteger(value) && value >= 2 && value <= 20))];
  if (!counts.length) return toast("Inserisci almeno un numero di topic tra 2 e 20.");
  const selected = state.dataset.papers.length - state.excluded.size;
  if (selected < 4) return toast("Seleziona almeno 4 documenti.");
  const overlay = $("#analysis-overlay");
  overlay.classList.remove("hidden");
  const progress = [
    "Pulizia scientifica e normalizzazione delle frasi…",
    "Stima parallela delle repliche indipendenti…",
    "Calcolo di UMass, NPMI, stabilità e diversità…",
    "Proiezione t-SNE e diagnostica dell'incertezza…",
    "Preparazione del pacchetto riproducibile…",
  ];
  let step = 0;
  const timer = setInterval(() => {
    $("#analysis-progress-text").textContent = progress[Math.min(++step, progress.length - 1)];
  }, 2200);
  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dataset_id: state.dataset.dataset_id,
        topic_counts: counts,
        mode: $("#analysis-mode").value,
        include_lsi: $("#include-lsi").checked,
        excluded_ids: [...state.excluded],
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Analisi non riuscita");
    state.result = payload;
    state.activeTopic = 1;
    state.topicAlgorithm = "lda";
    state.selectedK = payload.best_topic_number;
    state.mapYear = null;
    renderResults();
    navigate("results");
    toast(`Analisi verificata in ${fmt(payload.duration_seconds)} secondi.`);
  } catch (error) {
    toast(error.message);
  } finally {
    clearInterval(timer);
    overlay.classList.add("hidden");
  }
}

function renderResults() {
  const result = state.result;
  state.selectedK = state.selectedK || result.best_topic_number;
  $("#lda-model-select").innerHTML = result.lda_models.map(model =>
    `<option value="${model.topics_count}" ${model.topics_count===state.selectedK?"selected":""}>K=${model.topics_count}${model.recommended?" · raccomandato":""}</option>`
  ).join("");
  const availableYears = result.documents.map(document => document.year).filter(Boolean);
  const minYear = availableYears.length ? Math.min(...availableYears) : 0;
  const maxYear = availableYears.length ? Math.max(...availableYears) : 0;
  $("#map-year-filter").min = minYear;
  $("#map-year-filter").max = maxYear;
  $("#map-year-filter").value = maxYear;
  state.mapYear = maxYear;
  $("#map-year-value").textContent = maxYear || "tutti";
  const topicLabel = result.selection_mode === "optimized"
    ? "Topic ottimali"
    : result.selection_mode === "screening"
      ? "Topic esplorativi"
      : "Topic configurati";
  $("#result-kpis").dataset.topicLabel = topicLabel;
  $("#data-export").href = `/api/results/${result.analysis_id}/export`;
  $("#method-export").href = `/api/results/${result.analysis_id}/methodology`;
  $("#bundle-export").href = `/api/results/${result.analysis_id}/bundle`;
  $("#projection-label").textContent = result.methodology.projection;
  $("#topic-algorithm").value = "lda";
  $("#topic-algorithm").querySelector('option[value="lsi"]').disabled = !result.lsi;
  renderCoherence();
  renderSelectedModel();
  renderAuthors();
  renderCandidateTable();
}

function activateTab(name) {
  const button = $(`.result-tabs button[data-tab="${name}"]`);
  if (!button) return;
  $$(".result-tabs button").forEach(element => element.classList.toggle("active", element === button));
  $$(".tab-panel").forEach(element => element.classList.toggle("active", element.id === `tab-${name}`));
  if (name === "map") requestAnimationFrame(drawDocumentMap);
  if (name === "lda-explorer") requestAnimationFrame(renderLdaExplorer);
}

$$(".result-tabs button").forEach(button =>
  button.addEventListener("click", () => activateTab(button.dataset.tab))
);
$$(".model-jump").forEach(button =>
  button.addEventListener("click", () => activateTab(button.dataset.openTab))
);

$("#lda-model-select").addEventListener("change", event => {
  state.selectedK = Number(event.target.value);
  state.activeTopic = 1;
  renderSelectedModel();
});

function renderSelectedModel() {
  const result = state.result;
  const model = activeLdaModel();
  if (!model) return;
  const metrics = model.metrics;
  const topicLabel = model.recommended
    ? "Topic raccomandati"
    : "Topic scelti dall'utente";
  $("#active-model-description").textContent = model.recommended
    ? `K=${model.topics_count} · raccomandazione multi-metrica`
    : `K=${model.topics_count} · alternativa esplorabile`;
  $("#result-kpis").innerHTML = [
    ["Tempo totale", `${fmt(result.duration_seconds)} s`, result.mode],
    [topicLabel, model.topics_count, `${result.document_count} documenti`],
    ["Coerenza", fmt(metrics.coherence_npmi, 3), "NPMI ↑"],
    ["Stabilità", `${fmt(metrics.stability * 100, 1)}%`, `${metrics.runs} seed`],
  ].map(([label, value, suffix]) => statCard(label, value, suffix)).join("");
  renderYears();
  renderTopicSummary();
  if (state.topicAlgorithm === "lda") renderTopicExplorer();
  renderLdaExplorer();
  renderQuality();
  renderExternalValidation();
  renderBibliometrics();
  if ($("#tab-map").classList.contains("active")) requestAnimationFrame(drawDocumentMap);
}

function renderCoherence() {
  const data = state.result.algorithm_comparison;
  const width = 520, height = 220, padding = { l: 42, r: 18, t: 18, b: 30 };
  const values = data.flatMap(candidate => [candidate.lda_npmi, candidate.lsi_npmi]).filter(value => value !== null);
  let min = Math.min(...values), max = Math.max(...values);
  if (min === max) { min -= 0.1; max += 0.1; }
  const x = index => padding.l + index * (width - padding.l - padding.r) / Math.max(data.length - 1, 1);
  const y = value => padding.t + (max - value) * (height - padding.t - padding.b) / (max - min);
  const ldaPath = data.map((candidate, index) => `${index ? "L" : "M"} ${x(index)} ${y(candidate.lda_npmi)}`).join(" ");
  const lsiData = data.filter(candidate => candidate.lsi_npmi !== null);
  const lsiPath = lsiData.map((candidate, index) => `${index ? "L" : "M"} ${x(data.indexOf(candidate))} ${y(candidate.lsi_npmi)}`).join(" ");
  $("#coherence-chart").innerHTML = `<svg viewBox="0 0 ${width} ${height}" aria-label="Confronto coerenza NPMI LDA e LSI">
    <defs><linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2866ff" stop-opacity=".25"/><stop offset="1" stop-color="#2866ff" stop-opacity="0"/></linearGradient></defs>
    ${[0,.25,.5,.75,1].map(position => {
      const yy = padding.t + position * (height - padding.t - padding.b);
      return `<line class="chart-axis" x1="${padding.l}" y1="${yy}" x2="${width-padding.r}" y2="${yy}"/><text class="chart-text" x="3" y="${yy+3}">${(max-position*(max-min)).toFixed(2)}</text>`;
    }).join("")}
    <path class="chart-area" d="${ldaPath} L ${x(data.length-1)} ${height-padding.b} L ${x(0)} ${height-padding.b} Z"/>
    <path class="chart-line" d="${ldaPath}"/>
    ${lsiPath ? `<path d="${lsiPath}" fill="none" stroke="#ff9a48" stroke-width="3"/>` : ""}
    ${data.map((candidate,index) => `<circle class="chart-dot" cx="${x(index)}" cy="${y(candidate.lda_npmi)}" r="5"/>${candidate.lsi_npmi!==null?`<circle cx="${x(index)}" cy="${y(candidate.lsi_npmi)}" r="5" fill="white" stroke="#ff9a48" stroke-width="3"/>`:""}<text class="chart-text" x="${x(index)-4}" y="${height-8}">${candidate.topics}</text>`).join("")}
  </svg>`;
}

function renderYears() {
  const years = activeYears();
  const max = Math.max(1, ...years.flatMap(item => item.counts));
  $("#year-chart").innerHTML = years.map(item => `<div class="year-group">${
    item.counts.map((value,index) => `<i title="Topic ${index+1}: ${value}" style="height:${value/max*100}%;background:${colors[index%colors.length]}"></i>`).join("")
  }<span class="year-label">${item.year}</span></div>`).join("");
}

function renderTopicSummary() {
  $("#topic-summary").innerHTML = activeTopics().map((topic,index) => `
    <article class="topic-card" style="--topic-color:${colors[index%colors.length]}">
      <small>TOPIC ${topic.id} · ${topic.document_count} PAPER · PESO ${fmt(topic.weight_sum,1)}</small>
      <h3>${esc(topic.label)}</h3>
      <p>${topic.words.slice(3,8).map(word => esc(word.term)).join(" · ")}</p>
    </article>`).join("");
}

function renderTopicExplorer() {
  const isLsi = state.topicAlgorithm === "lsi" && state.result.lsi;
  const topics = isLsi ? state.result.lsi.topics : activeTopics();
  $("#algorithm-description").textContent = isLsi
    ? "LSI · salienza relativa dei componenti, non probabilità"
    : "LDA · probabilità per documento";
  $("#topic-selector").innerHTML = topics.map((topic,index) => `
    <button class="topic-select-button ${topic.id===state.activeTopic?"active":""}" data-topic="${topic.id}" style="--topic-color:${colors[index%colors.length]}">
      <strong>Topic ${topic.id}</strong><span>${esc(topic.label)} · ${topic.document_count} paper</span>
    </button>`).join("");
  $$(".topic-select-button").forEach(button => button.addEventListener("click", () => {
    state.activeTopic = Number(button.dataset.topic);
    renderTopicExplorer();
  }));
  const topic = topics[state.activeTopic - 1] || topics[0];
  const wordScore = word => isLsi ? Math.abs(word.loading) : word.weight;
  const maxWeight = Math.max(...topic.words.slice(0, 28).map(wordScore), 1e-9);
  $("#word-cloud").innerHTML = topic.words.slice(0,28).map((word,index) => {
    const score = wordScore(word);
    const size = 11 + 25 * Math.sqrt(score / maxWeight);
    return `<span class="cloud-word" title="Esclusività ${fmt(word.exclusivity*100,1)}%" style="font-size:${size}px;color:${colors[(index+state.activeTopic-1)%colors.length]};opacity:${.62+.38*(score/maxWeight)}">${esc(word.term)}</span>`;
  }).join("");
  $(".term-table-wrap thead").innerHTML = isLsi
    ? "<tr><th>Termine</th><th>Loading</th><th>Esclusività</th><th>Nota</th></tr>"
    : "<tr><th>Termine</th><th>Frequenza</th><th>Log lift</th><th>Log prob</th></tr>";
  $("#term-table").innerHTML = topic.words.map(word => isLsi
    ? `<tr><td><b>${esc(word.term)}</b></td><td>${fmt(word.loading,5)}</td><td>${fmt(word.exclusivity*100,1)}%</td><td>componente firmata</td></tr>`
    : `<tr><td><b>${esc(word.term)}</b></td><td>${word.frequency}</td><td>${fmt(word.log_lift,4)}</td><td>${fmt(word.log_prob,4)}</td></tr>`
  ).join("");
  $("#topic-documents").innerHTML = topic.documents.slice(0,20).map((document,index) => {
    const score = isLsi ? document.salience : document.weight;
    return `<div class="document-item"><span class="doc-rank">${index+1}</span><div><strong>${esc(document.title)}</strong><small>${esc(document.authors)} · ${document.year||"s.d."}</small></div><span class="confidence">${fmt(score*100,1)}%</span></div>`;
  }).join("");
}

$("#topic-algorithm").addEventListener("change", event => {
  state.topicAlgorithm = event.target.value;
  state.activeTopic = 1;
  renderTopicExplorer();
});

function renderLdaExplorer() {
  const model = activeLdaModel();
  if (!model) return;
  const topic = model.topics[state.activeTopic - 1] || model.topics[0];
  if (!topic) return;
  const selectedTopic = topic.id;
  const coordinates = model.topic_coordinates;
  const maxPrevalence = Math.max(...coordinates.map(item => item.prevalence), 1e-9);
  $("#intertopic-map").innerHTML = `
    <line x1="45" y1="240" x2="575" y2="240" class="intertopic-axis"/>
    <line x1="310" y1="35" x2="310" y2="445" class="intertopic-axis"/>
    <text x="550" y="232" class="intertopic-label">PC1</text>
    <text x="318" y="52" class="intertopic-label">PC2</text>
    ${coordinates.map((item,index) => {
      const x = 70 + item.x * 480;
      const y = 420 - item.y * 360;
      const radius = 25 + 53 * Math.sqrt(item.prevalence / maxPrevalence);
      return `<g class="topic-bubble ${item.topic===selectedTopic?"selected":""}" data-topic="${item.topic}">
        <circle cx="${x}" cy="${y}" r="${radius}" fill="${colors[index%colors.length]}"/>
        <text x="${x}" y="${y+5}" text-anchor="middle">${item.topic}</text>
        <title>Topic ${item.topic} · ${fmt(item.prevalence*100,1)}% del peso</title>
      </g>`;
    }).join("")}
  `;
  $$(".topic-bubble").forEach(bubble => bubble.addEventListener("click", () => {
    state.activeTopic = Number(bubble.dataset.topic);
    renderLdaExplorer();
    if (state.topicAlgorithm === "lda") renderTopicExplorer();
  }));
  renderRelevantTerms(topic);
}

function renderRelevantTerms(topic) {
  const lambda = Number($("#lambda-slider").value);
  $("#lambda-value").textContent = fmt(lambda, 2);
  $("#relevant-terms-title").textContent = `Top termini · Topic ${topic.id} (${fmt(topic.prevalence*100,1)}% del peso)`;
  const terms = [...topic.words]
    .map(word => ({
      ...word,
      relevance: lambda * word.log_prob + (1 - lambda) * word.log_lift,
    }))
    .sort((first, second) => second.relevance - first.relevance)
    .slice(0, 30);
  const maxFrequency = Math.max(
    ...terms.flatMap(word => [word.frequency, word.topic_frequency]), 1
  );
  $("#relevant-terms-chart").innerHTML = terms.map(word => `
    <div class="relevance-row" title="rilevanza ${fmt(word.relevance,4)} · log lift ${fmt(word.log_lift,4)}">
      <b>${esc(word.term)}</b>
      <span class="relevance-bars">
        <i class="overall-frequency" style="width:${word.frequency/maxFrequency*100}%"></i>
        <i class="topic-frequency" style="width:${word.topic_frequency/maxFrequency*100}%"></i>
      </span>
      <small>${fmt(word.topic_frequency,1)}</small>
    </div>`).join("") + `
      <div class="relevance-legend">
        <span><i class="overall-frequency"></i>frequenza nel corpus</span>
        <span><i class="topic-frequency"></i>frequenza stimata nel topic</span>
      </div>`;
}

$("#lambda-slider").addEventListener("input", () => {
  const topic = activeLdaModel()?.topics[state.activeTopic - 1];
  if (topic) renderRelevantTerms(topic);
});

function drawDocumentMap() {
  const canvas = $("#document-map");
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = rect.width * ratio;
  canvas.height = rect.height * ratio;
  const context = canvas.getContext("2d");
  context.scale(ratio, ratio);
  const width = rect.width, height = rect.height, padding = 30;
  const assignments = activeAssignments();
  const cutoff = state.mapYear;
  const documents = state.result.documents
    .filter(document => !cutoff || !document.year || document.year <= cutoff)
    .map(document => ({ ...document, ...(assignments[document.id] || {}) }));
  const byId = Object.fromEntries(documents.map(document => [document.id, document]));
  context.strokeStyle = "rgba(80,100,130,.08)";
  state.result.connections.forEach(edge => {
    const first = byId[edge.source], second = byId[edge.target];
    if (!first || !second) return;
    context.beginPath();
    context.moveTo(padding + first.x*(width-2*padding), padding + first.y*(height-2*padding));
    context.lineTo(padding + second.x*(width-2*padding), padding + second.y*(height-2*padding));
    context.stroke();
  });
  documents.forEach(document => {
    const x = padding + document.x*(width-2*padding), y = padding + document.y*(height-2*padding);
    context.beginPath();
    context.fillStyle = document.uncertain ? "#aab2bf" : colors[(document.topic-1)%colors.length];
    context.globalAlpha = document.uncertain ? 0.58 : 0.8;
    context.arc(x, y, 3 + document.confidence*4, 0, Math.PI*2);
    context.fill();
  });
  const model = activeLdaModel();
  $("#map-legend").innerHTML = (model?.topics || []).map((topic,index) =>
    `<span><i style="background:${colors[index%colors.length]}"></i>Topic ${topic.id} · ${esc(topic.label)}</span>`
  ).join("") + `<span><i style="background:#aab2bf"></i>assegnazione incerta</span>`;
  context.globalAlpha = 1;
  canvas.onmousemove = event => {
    const nearest = documents.map(document => ({
      document,
      distance: Math.hypot(
        event.offsetX-(padding+document.x*(width-2*padding)),
        event.offsetY-(padding+document.y*(height-2*padding)),
      ),
    })).sort((a,b) => a.distance-b.distance)[0];
    const tooltip = $("#map-tooltip");
    if (nearest && nearest.distance < 12) {
      tooltip.innerHTML = `<b>${esc(nearest.document.title)}</b><br>Topic ${nearest.document.topic} · ${fmt(nearest.document.confidence*100,1)}%${nearest.document.uncertain?" · incerto":""}`;
      tooltip.style.left = `${Math.min(event.offsetX+30,width-250)}px`;
      tooltip.style.top = `${event.offsetY+65}px`;
      tooltip.classList.remove("hidden");
    } else tooltip.classList.add("hidden");
  };
}

$("#map-year-filter").addEventListener("input", event => {
  state.mapYear = Number(event.target.value);
  $("#map-year-value").textContent = state.mapYear;
  drawDocumentMap();
});

window.addEventListener("resize", () => {
  if ($("#tab-map").classList.contains("active") && state.result) drawDocumentMap();
});

function renderAuthors() {
  const authors = state.result.authors.slice(0,15);
  const max = Math.max(1, ...authors.map(author => author.papers));
  $("#author-bars").innerHTML = authors.map(author => `<div class="author-row"><b title="${esc(author.name)}">${esc(author.name)}</b><span class="author-track"><i style="width:${author.papers/max*100}%"></i></span><span>${author.papers}</span></div>`).join("") || "<p>Nomi degli autori non disponibili.</p>";
  $("#coauthor-list").innerHTML = state.result.coauthors.slice(0,30).map(edge => `<div class="connection"><b>${esc(edge.source)}</b><i data-count="${edge.papers}"></i><b>${esc(edge.target)}</b></div>`).join("") || "<p>Nessuna co-autorialità rilevata.</p>";
}

function diagnosticRow(label, value, display, threshold = 0.7) {
  const percentage = Math.max(0, Math.min(100, value * 100));
  const badgeClass = value >= threshold ? "good" : "warn";
  return `<div class="diagnostic-row"><span>${label}</span><span class="diagnostic-track"><i style="width:${percentage}%"></i></span><b class="quality-badge ${badgeClass}">${display}</b></div>`;
}

function renderQuality() {
  const model = activeLdaModel();
  const assignments = activeAssignments();
  const documents = state.result.documents.map(document => ({
    ...document,
    ...(assignments[document.id] || {}),
  }));
  const strongAssignments = documents.filter(document => document.confidence >= .70).length;
  const uncertain = documents.filter(document => document.uncertain)
    .sort((first,second) => second.entropy-first.entropy || first.confidence-second.confidence);
  const quality = {
    ...state.result.quality,
    strong_assignments: strongAssignments,
    strong_assignment_rate: strongAssignments / Math.max(documents.length, 1),
    uncertain_documents: uncertain.length,
    uncertain_rate: uncertain.length / Math.max(documents.length, 1),
    mean_confidence: documents.reduce((sum,document) => sum+document.confidence,0) / Math.max(documents.length,1),
    uncertain,
  };
  $("#quality-stats").innerHTML = [
    ["Assegnazioni forti", `${fmt(quality.strong_assignment_rate*100,1)}%`, `${quality.strong_assignments} paper`],
    ["Documenti incerti", quality.uncertain_documents, `${fmt(quality.uncertain_rate*100,1)}%`],
    ["Outlier semantici", quality.semantic_outliers, "da controllare"],
    ["Confidenza media", `${fmt(quality.mean_confidence*100,1)}%`, "probabilità massima"],
  ].map(([label,value,suffix]) => statCard(label,value,suffix)).join("");
  $("#uncertain-documents").innerHTML = quality.uncertain.slice(0,40).map(document => `
    <div class="audit-item">
      <strong>${esc(document.title)}</strong><small>${esc(document.authors)} · ${document.year||"s.d."}</small>
      <div class="audit-metrics"><span>Topic ${document.topic}: ${fmt(document.confidence*100,1)}%</span><span>Topic ${document.second_topic}: ${fmt(document.second_weight*100,1)}%</span><span>Entropia ${fmt(document.entropy,2)}</span>${document.semantic_outlier?'<span>Outlier semantico</span>':""}</div>
    </div>`).join("") || "<p>Nessun documento supera le soglie di incertezza.</p>";
  $("#quality-diagnostics").innerHTML = [
    diagnosticRow("Stabilità multi-seed", model.metrics.stability, `${fmt(model.metrics.stability*100,1)}%`, .65),
    diagnosticRow("Topic diversity", model.metrics.diversity, `${fmt(model.metrics.diversity*100,1)}%`, .7),
    diagnosticRow("Esclusività", model.metrics.exclusivity, `${fmt(model.metrics.exclusivity*100,1)}%`, .55),
    diagnosticRow("Assegnazioni forti", quality.strong_assignment_rate, `${fmt(quality.strong_assignment_rate*100,1)}%`, .7),
    diagnosticRow("Copertura abstract", quality.abstract_coverage, `${fmt(quality.abstract_coverage*100,1)}%`, .9),
    diagnosticRow("Copertura keyword", quality.keyword_coverage, `${fmt(quality.keyword_coverage*100,1)}%`, .75),
  ].join("");
}

$("#myslr-comparison-file").addEventListener("change", async event => {
  const file = event.target.files[0];
  if (!file || !state.result) return;
  const body = new FormData();
  body.append("file", file);
  toast("Confronto MySLR in corso…");
  try {
    const response = await fetch(
      `/api/results/${state.result.analysis_id}/compare-myslr`,
      { method: "POST", body },
    );
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Confronto non riuscito");
    state.result.external_validation = payload;
    renderExternalValidation();
    toast(`${payload.reference_documents} assegnazioni MySLR confrontate.`);
  } catch (error) {
    toast(error.message);
  } finally {
    event.target.value = "";
  }
});

function renderExternalValidation() {
  const validation = state.result.external_validation;
  const container = $("#external-validation");
  if (!validation) {
    container.classList.add("hidden");
    return;
  }
  const selected = validation.comparisons.find(
    comparison => comparison.topics === state.selectedK
  ) || validation.comparisons[0];
  container.classList.remove("hidden");
  container.innerHTML = `
    <div class="validation-summary">
      ${statCard("Copertura", `${fmt(selected.coverage*100,1)}%`, `${selected.matched_documents} paper`)}
      ${statCard("ARI", fmt(selected.adjusted_rand_index,4), "1 = accordo")}
      ${statCard("NMI", fmt(selected.normalized_mutual_information,4), "1 = accordo")}
      ${statCard("Accuratezza allineata", `${fmt(selected.aligned_accuracy*100,1)}%`, "migliore permutazione")}
    </div>
    <div class="validation-details">
      <div>
        <small>MATRICE MYSLR → SLR LENS · K=${selected.topics}</small>
        <table class="contingency-table">
          <thead><tr><th>MySLR</th>${Array.from({length:selected.topics},(_,index)=>`<th>SLR ${index+1}</th>`).join("")}</tr></thead>
          <tbody>${selected.contingency_matrix.map((row,index)=>`<tr><th>${esc(validation.reference_topics[index])}</th>${row.map(value=>`<td>${value}</td>`).join("")}</tr>`).join("")}</tbody>
        </table>
      </div>
      <div class="validation-interpretation">
        <strong>${selected.adjusted_rand_index >= .65 ? "Accordo forte" : selected.adjusted_rand_index >= .30 ? "Accordo parziale" : "Soluzioni sostanzialmente diverse"}</strong>
        <p>ARI e NMI non dipendono dai numeri assegnati ai topic. Valori vicini a zero indicano poca concordanza, ma non stabiliscono quale modello sia corretto.</p>
        <small>${selected.doi_matches} match DOI · ${selected.title_matches} match titolo · file ${esc(validation.source_file)}</small>
      </div>
    </div>`;
}

function renderBibliometricsLegacy() {
  const metrics = state.result.bibliometrics;
  const assignments = activeAssignments();
  const topicImpact = activeTopics().map(topic => {
    const documents = state.result.documents.filter(
      document => assignments[document.id]?.topic === topic.id
    );
    const citations = documents.reduce((sum,document) => sum+document.citations,0);
    return {
      topic: topic.id,
      papers: documents.length,
      citations,
      mean_citations: citations / Math.max(documents.length,1),
    };
  });
  $("#bibliometric-stats").innerHTML = [
    ["Citazioni totali", fmt(metrics.total_citations,0), "nel corpus"],
    ["Media citazioni", fmt(metrics.mean_citations,1), "per paper"],
    ["Open Access", `${fmt(metrics.open_access_rate*100,1)}%`, `${metrics.open_access_count} paper`],
    ["Fonti distinte", metrics.sources_count, "riviste/proceedings"],
  ].map(([label,value,suffix]) => statCard(label,value,suffix)).join("");
  const sources = metrics.top_sources.slice(0,15);
  const max = Math.max(1,...sources.map(source => source.papers));
  $("#source-bars").innerHTML = sources.map(source => `<div class="author-row"><b title="${esc(source.name)}">${esc(source.name)}</b><span class="author-track"><i style="width:${source.papers/max*100}%"></i></span><span>${source.papers}</span></div>`).join("") || "<p>Fonti non disponibili.</p>";
  $("#topic-impact").innerHTML = topicImpact.map((topic,index) => `<div class="impact-card" style="--topic-color:${colors[index%colors.length]}"><small>TOPIC ${topic.topic} · ${topic.papers} PAPER</small><strong>${fmt(topic.citations,0)}</strong><span>citazioni · media ${fmt(topic.mean_citations,1)}</span></div>`).join("");
  $("#document-types").innerHTML = metrics.document_types.map(item => `<span>${esc(item.name)} <b>${item.papers}</b></span>`).join("") || "<p>Tipologie non disponibili.</p>";
  const quality = state.result.quality;
  $("#metadata-coverage").innerHTML = [
    diagnosticRow("Abstract", quality.abstract_coverage, `${fmt(quality.abstract_coverage*100,1)}%`, .9),
    diagnosticRow("Author keywords", quality.keyword_coverage, `${fmt(quality.keyword_coverage*100,1)}%`, .75),
    diagnosticRow("DOI validi", quality.doi_coverage, `${fmt(quality.doi_coverage*100,1)}%`, .85),
    diagnosticRow("Open Access", metrics.open_access_rate, `${fmt(metrics.open_access_rate*100,1)}%`, .5),
  ].join("");
}

function renderBibliometrics() {
  const metrics = state.result.bibliometrics;
  const assignments = activeAssignments();
  const topicImpact = activeTopics().map(topic => {
    const documents = state.result.documents.filter(
      document => assignments[document.id]?.topic === topic.id
    );
    const citations = documents.reduce((sum,document) => sum+document.citations,0);
    return { topic:topic.id, papers:documents.length, citations,
      mean_citations:citations/Math.max(documents.length,1) };
  });
  $("#bibliometric-stats").innerHTML = [
    ["Citazioni totali", fmt(metrics.total_citations,0), "nel corpus"],
    ["Media citazioni", fmt(metrics.mean_citations,1), "per paper"],
    ["Crescita annua", `${fmt(metrics.annual_growth_rate*100,1)}%`, "CAGR produzione"],
    ["Collaborazione", `${fmt(metrics.collaboration.multi_authored_rate*100,1)}%`, "paper multi-autore"],
  ].map(([label,value,suffix]) => statCard(label,value,suffix)).join("");

  const intellectual = metrics.intellectual;
  $("#reference-coverage-badge").innerHTML = intellectual.available
    ? `<div class="coverage-pill"><strong>${fmt(intellectual.references_coverage*100,1)}%</strong>references disponibili</div>`
    : `<div class="coverage-pill"><strong>Metadata-aware</strong>nessun risultato inventato</div>`;
  $("#growth-rate").textContent = `${fmt(metrics.annual_growth_rate*100,1)}% CAGR`;
  renderAnnualProduction(metrics.annual_production);

  const sources=metrics.top_sources.slice(0,15);
  const max=Math.max(1,...sources.map(source=>source.papers));
  $("#source-bars").innerHTML=sources.map(source=>`<div class="author-row"><b title="${esc(source.name)}">${esc(source.name)}</b><span class="author-track"><i style="width:${source.papers/max*100}%"></i></span><span>${source.papers}</span></div>`).join("")||"<p>Fonti non disponibili.</p>";
  $("#bradford-zones").innerHTML=metrics.bradford.zones.map(zone=>`<div class="bradford-zone"><small>ZONA ${zone.zone}</small><strong>${zone.sources}</strong><span>fonti · ${zone.papers} paper</span></div>`).join("");
  $("#topic-impact").innerHTML=topicImpact.map((topic,index)=>`<div class="impact-card" style="--topic-color:${colors[index%colors.length]}"><small>TOPIC ${topic.topic} · ${topic.papers} PAPER</small><strong>${fmt(topic.citations,0)}</strong><span>citazioni · media ${fmt(topic.mean_citations,1)}</span></div>`).join("");
  $("#most-cited-documents").innerHTML=metrics.most_cited_documents.slice(0,12).map((document,index)=>`<div class="rank-row"><i>${index+1}</i><b title="${esc(document.title)}">${esc(document.title)}</b><small>${document.citations} cit.</small></div>`).join("");
  $("#document-types").innerHTML=metrics.document_types.map(item=>`<span>${esc(item.name)} <b>${item.papers}</b></span>`).join("")||"<p>Tipologie non disponibili.</p>";
  const quality=state.result.quality;
  $("#metadata-coverage").innerHTML=[
    diagnosticRow("Abstract",quality.abstract_coverage,`${fmt(quality.abstract_coverage*100,1)}%`,.9),
    diagnosticRow("Author keywords",quality.keyword_coverage,`${fmt(quality.keyword_coverage*100,1)}%`,.75),
    diagnosticRow("DOI validi",quality.doi_coverage,`${fmt(quality.doi_coverage*100,1)}%`,.85),
    diagnosticRow("Open Access",metrics.open_access_rate,`${fmt(metrics.open_access_rate*100,1)}%`,.5),
  ].join("");

  $("#lotka-beta").textContent=`Lotka β=${fmt(metrics.lotka.estimated_beta,2)}`;
  $("#author-impact").innerHTML=`<div class="rank-row author-impact-row"><i>#</i><b>Autore</b><span>Paper</span><span>h</span><span>g</span><span>m</span></div>`+
    metrics.authors.slice(0,18).map((author,index)=>`<div class="rank-row author-impact-row"><i>${index+1}</i><b title="${esc(author.name)}">${esc(author.name)}</b><span>${author.papers}</span><span>${author.h_index}</span><span>${author.g_index}</span><span>${fmt(author.m_index,2)}</span></div>`).join("");
  $("#collaboration-stats").innerHTML=[
    ["Autori",metrics.authors_count,"distinti"],["Paesi",metrics.countries_count,"identificati"],
    ["Autori/documento",fmt(metrics.collaboration.authors_per_document,1),"media"],
    ["Collaboration index",fmt(metrics.collaboration.collaboration_index,1),"autori / paper collaborativo"],
  ].map(([label,value,suffix])=>statCard(label,value,suffix)).join("");
  renderNetwork("#coauthor-network",metrics.coauthor_network,"author");
  renderCountries(metrics.countries);
  renderNetwork("#country-network",metrics.country_network,"country",true);
  const affiliations=metrics.top_affiliations.slice(0,15);
  const affiliationMax=Math.max(1,...affiliations.map(item=>item.papers));
  $("#affiliation-bars").innerHTML=affiliations.map(item=>`<div class="author-row"><b title="${esc(item.name)}">${esc(item.name)}</b><span class="author-track"><i style="width:${item.papers/affiliationMax*100}%"></i></span><span>${item.papers}</span></div>`).join("")||"<p>Affiliazioni non disponibili nell'export.</p>";

  renderNetwork("#keyword-network",metrics.conceptual.keyword_network,"keyword");
  renderThematicMap(metrics.conceptual.thematic_map);
  renderTrendTopics(metrics.conceptual.trend_topics);
  renderThreeFields(metrics.conceptual.three_fields);
  renderThematicEvolution(metrics.conceptual.thematic_evolution);

  const gate=$("#intellectual-gate");
  gate.classList.toggle("ready",intellectual.available);
  gate.innerHTML=intellectual.available
    ? `<strong>Struttura intellettuale calcolata su dati reali</strong><p>Copertura cited references: ${fmt(intellectual.references_coverage*100,1)}%. Le reti usano esclusivamente riferimenti presenti nell'export.</p>`
    : `<strong>Analisi correttamente sospesa</strong><p>${esc(intellectual.reason)} Esporta da Scopus anche “References” e ricarica il corpus: il modulo si attiverà automaticamente.</p>`;
  $("#intellectual-content").classList.toggle("hidden",!intellectual.available);
  if(intellectual.available){
    renderNetwork("#cocitation-network",intellectual.cocitation_network,"reference");
    $("#coupling-list").innerHTML=intellectual.bibliographic_coupling.slice(0,40).map(edge=>`<div class="connection"><span title="${esc(edge.source)}">${esc(edge.source)}</span><i data-count="${edge.shared_references}"></i><span title="${esc(edge.target)}">${esc(edge.target)}</span></div>`).join("");
  }
  $$("[data-biblio-jump]").forEach(button=>button.onclick=()=>$(`#biblio-${button.dataset.biblioJump}`).scrollIntoView({behavior:"smooth",block:"start"}));
}

function renderAnnualProduction(series){
  if(!series.length){$("#annual-production").innerHTML="<p>Anni non disponibili.</p>";return;}
  const width=620,height=250,pad=34,max=Math.max(1,...series.map(item=>item.papers));
  const step=(width-pad*2)/Math.max(series.length,1);
  const bars=series.map((item,index)=>{const h=item.papers/max*(height-pad*2),x=pad+index*step+step*.18,y=height-pad-h;
    return `<g><rect x="${x}" y="${y}" width="${Math.max(5,step*.64)}" height="${h}" rx="4" fill="#2866ff"/><text x="${x+step*.32}" y="${height-12}" text-anchor="middle" class="chart-text">${item.year}</text><text x="${x+step*.32}" y="${Math.max(12,y-6)}" text-anchor="middle" class="chart-text">${item.papers}</text></g>`;}).join("");
  $("#annual-production").innerHTML=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Produzione scientifica annuale"><line x1="${pad}" y1="${height-pad}" x2="${width-pad}" y2="${height-pad}" class="chart-axis"/>${bars}</svg>`;
}

function renderNetwork(selector,network,kind,compact=false){
  const container=$(selector);
  if(!network?.nodes?.length||!network?.edges?.length){container.innerHTML="<p class='empty-state'>Rete non disponibile con i metadati correnti.</p>";return;}
  const width=700,height=compact?135:290,cx=width/2,cy=height/2,nodes=network.nodes.slice(0,compact?18:35);
  const allowed=new Set(nodes.map(node=>node.id)),maxDegree=Math.max(1,...nodes.map(node=>node.degree)),positions={};
  nodes.forEach((node,index)=>{const angle=index/nodes.length*Math.PI*2-Math.PI/2,ring=index<Math.min(7,nodes.length)?.48:.85;positions[node.id]=[cx+Math.cos(angle)*width*.38*ring,cy+Math.sin(angle)*height*.40*ring];});
  const edges=network.edges.filter(edge=>allowed.has(edge.source)&&allowed.has(edge.target)).slice(0,90).map(edge=>{const [x1,y1]=positions[edge.source],[x2,y2]=positions[edge.target];return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" class="network-edge" stroke-width="${Math.min(5,.5+edge.weight*.55)}"><title>${esc(edge.source)} ↔ ${esc(edge.target)}: ${edge.weight}</title></line>`;}).join("");
  const circles=nodes.map((node,index)=>{const [x,y]=positions[node.id],r=3+Math.sqrt(node.degree/maxDegree)*8,color=colors[index%colors.length],label=kind==="reference"&&node.label.length>30?node.label.slice(0,28)+"…":node.label;return `<g><circle cx="${x}" cy="${y}" r="${r}" fill="${color}" class="network-node"><title>${esc(node.label)} · grado ${node.degree}</title></circle>${compact?"":`<text x="${x+r+3}" y="${y+3}" class="network-label">${esc(label)}</text>`}</g>`;}).join("");
  container.innerHTML=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Rete ${kind}">${edges}${circles}</svg>`;
}

function renderCountries(countries){
  const max=Math.max(1,...countries.map(country=>country.papers));
  $("#country-collaboration").innerHTML=countries.slice(0,14).map(country=>`<div class="country-row"><b>${esc(country.name)}</b><span class="country-bar"><i style="width:${country.scp/max*100}%"></i><i style="width:${country.mcp/max*100}%"></i></span><small>${country.papers} · MCP ${fmt(country.mcp_rate*100,0)}%</small></div>`).join("")||"<p>Paesi non riconosciuti nelle affiliazioni.</p>";
}

function renderThematicMap(themes){
  if(!themes.length){$("#thematic-map").innerHTML="<p>Servono keyword sufficienti per costruire la mappa.</p>";return;}
  const width=620,height=285,pad=42,maxX=Math.max(1,...themes.map(theme=>Math.abs(theme.centrality_relative))),maxY=Math.max(1,...themes.map(theme=>Math.abs(theme.density_relative))),maxDocuments=Math.max(1,...themes.map(theme=>theme.documents));
  const bubbles=themes.slice(0,12).map((theme,index)=>{const x=pad+(theme.centrality_relative/maxX+1)/2*(width-pad*2),y=height-pad-(theme.density_relative/maxY+1)/2*(height-pad*2),r=10+Math.sqrt(theme.documents/maxDocuments)*22;return `<g><circle cx="${x}" cy="${y}" r="${r}" fill="${colors[index%colors.length]}" class="theme-bubble"><title>${esc(theme.label)} · centralità ${fmt(theme.centrality,1)} · densità ${fmt(theme.density,1)}</title></circle><text x="${x}" y="${y+3}" text-anchor="middle" class="theme-label">${esc(theme.label.slice(0,22))}</text></g>`;}).join("");
  $("#thematic-map").innerHTML=`<svg viewBox="0 0 ${width} ${height}"><text x="14" y="17" class="quadrant-label">NICCHIA</text><text x="${width-88}" y="17" class="quadrant-label">MOTORI</text><text x="14" y="${height-10}" class="quadrant-label">DECLINO/EMERGENTI</text><text x="${width-93}" y="${height-10}" class="quadrant-label">BASIC THEMES</text>${bubbles}</svg>`;
}

function renderTrendTopics(topics){
  $("#trend-topics").innerHTML=topics.slice(0,16).map(topic=>{const max=Math.max(1,...topic.series.map(point=>point.papers));return `<div class="trend-card"><b title="${esc(topic.keyword)}">${esc(topic.keyword)}</b><small>${topic.total} occorrenze</small><span class="trend-spark">${topic.series.map(point=>`<i style="height:${Math.max(4,point.papers/max*100)}%" title="${point.year}: ${point.papers}"></i>`).join("")}</span></div>`;}).join("")||"<p>Keyword temporali non disponibili.</p>";
}

function renderThreeFields(flows){
  const first=flows.author_keyword.slice(0,24),second=flows.keyword_source.slice(0,24);
  if(!first.length||!second.length){$("#three-field-plot").innerHTML="<p>Servono autori, keyword e fonti per il Three-Field Plot.</p>";return;}
  const authors=[...new Set(first.map(edge=>edge.source))].slice(0,8);
  const keywords=[...new Set([...first.map(edge=>edge.target),...second.map(edge=>edge.source)])].slice(0,10);
  const sources=[...new Set(second.map(edge=>edge.target))].slice(0,8);
  const columns=[authors,keywords,sources],width=700,height=285,positions={};
  columns.forEach((items,column)=>items.forEach((item,index)=>positions[`${column}:${item}`]=[45+column*305,28+index*(230/Math.max(items.length-1,1))]));
  const links=[
    ...first.filter(edge=>authors.includes(edge.source)&&keywords.includes(edge.target)).map(edge=>({...edge,a:`0:${edge.source}`,b:`1:${edge.target}`})),
    ...second.filter(edge=>keywords.includes(edge.source)&&sources.includes(edge.target)).map(edge=>({...edge,a:`1:${edge.source}`,b:`2:${edge.target}`})),
  ].map(edge=>{const [x1,y1]=positions[edge.a],[x2,y2]=positions[edge.b];return `<path d="M${x1+13},${y1} C${x1+145},${y1} ${x2-145},${y2} ${x2-13},${y2}" class="flow-line" stroke-width="${Math.min(8,1+edge.weight)}"><title>${esc(edge.source)} → ${esc(edge.target)}: ${edge.weight}</title></path>`;}).join("");
  const nodes=columns.flatMap((items,column)=>items.map((item,index)=>{const [x,y]=positions[`${column}:${item}`],color=colors[(column*2+index)%colors.length],anchor=column===2?"end":"start",labelX=column===2?x-17:x+17;return `<g><rect x="${x-11}" y="${y-6}" width="22" height="12" fill="${color}" class="flow-node"/><text x="${labelX}" y="${y+3}" text-anchor="${anchor}" class="flow-label">${esc(item.slice(0,24))}</text></g>`;})).join("");
  $("#three-field-plot").innerHTML=`<svg viewBox="0 0 ${width} ${height}">${links}${nodes}</svg>`;
}

function renderThematicEvolution(evolution){
  if(!evolution?.slices?.length||evolution.slices.length<2){$("#thematic-evolution").innerHTML="<p>Servono almeno due anni per l'evoluzione tematica.</p>";return;}
  const left=evolution.slices[0].themes.slice(0,8),right=evolution.slices[1].themes.slice(0,8),width=700,height=285,positions={};
  left.forEach((theme,index)=>positions[theme.id]=[75,35+index*30]);
  right.forEach((theme,index)=>positions[theme.id]=[625,35+index*30]);
  const allowed=new Set([...left,...right].map(theme=>theme.id));
  const flows=evolution.flows.filter(flow=>allowed.has(flow.source)&&allowed.has(flow.target)).slice(0,25).map(flow=>{const [x1,y1]=positions[flow.source],[x2,y2]=positions[flow.target];return `<path d="M${x1+12},${y1} C280,${y1} 420,${y2} ${x2-12},${y2}" class="flow-line" stroke-width="${Math.max(1,flow.jaccard*10)}"><title>Jaccard ${fmt(flow.jaccard,2)} · ${esc(flow.shared_keywords.join(", "))}</title></path>`;}).join("");
  const nodes=[...left,...right].map((theme,index)=>{const [x,y]=positions[theme.id];return `<g><circle cx="${x}" cy="${y}" r="${7+Math.min(10,Math.sqrt(theme.documents))}" fill="${colors[index%colors.length]}"/><text x="${x+(x<350?18:-18)}" y="${y+3}" text-anchor="${x<350?"start":"end"}" class="flow-label">${esc(theme.label.slice(0,30))}</text></g>`;}).join("");
  const a=evolution.slices[0],b=evolution.slices[1];
  $("#thematic-evolution").innerHTML=`<svg viewBox="0 0 ${width} ${height}"><text x="20" y="14" class="quadrant-label">${a.start_year}–${a.end_year}</text><text x="${width-80}" y="14" class="quadrant-label">${b.start_year}–${b.end_year}</text>${flows}${nodes}</svg>`;
}

function renderCandidateTable() {
  const result = state.result;
  const lsiByK = Object.fromEntries((result.lsi?.candidates || []).map(candidate => [candidate.topics, candidate]));
  $("#candidate-table").innerHTML = `
    <p class="selection-note">${
      result.selection_mode === "optimized"
        ? "Il candidato selezionato massimizza un rank aggregato dichiarato su repliche indipendenti; tutte le metriche restano visibili."
        : result.selection_mode === "screening"
          ? "Screening rapido con un solo seed: utile per esplorare, non certifica un optimum stabile."
          : "È stato valutato un solo K: configurazione richiesta, non optimum dimostrato."
    }</p>
    <table class="paper-table"><thead><tr><th>K</th><th>LDA NPMI ↑</th><th>LSI NPMI ↑</th><th>LDA stabilità</th><th>LSI stabilità</th><th>LDA perplexity ↓</th><th>LSI varianza</th><th>Repliche</th><th>Esito</th><th></th></tr></thead><tbody>${
      result.candidates.map(candidate => { const lsi=lsiByK[candidate.topics]; return `<tr>
        <td><b>${candidate.topics}</b></td><td>${fmt(candidate.coherence_npmi,4)}</td><td>${lsi?fmt(lsi.coherence_npmi,4):"—"}</td>
        <td>${fmt(candidate.stability*100,1)}%</td><td>${lsi?fmt(lsi.stability*100,1)+"%":"—"}</td>
        <td>${fmt(candidate.perplexity,1)}</td><td>${lsi?fmt(lsi.explained_variance*100,1)+"%":"—"}</td><td>${candidate.runs}</td>
        <td>${candidate.topics===result.best_topic_number?'<b style="color:#249c65">LDA</b>':""}${lsi&&lsi.topics===result.lsi.best_topic_number?' <b style="color:#d96b21">LSI</b>':""}</td>
        <td><button class="table-action" data-select-k="${candidate.topics}">Esplora</button></td>
      </tr>`}).join("")
    }</tbody></table>`;
  $$("[data-select-k]").forEach(button => button.addEventListener("click", () => {
    state.selectedK = Number(button.dataset.selectK);
    state.activeTopic = 1;
    $("#lda-model-select").value = state.selectedK;
    renderSelectedModel();
    activateTab("lda-explorer");
  }));
}
