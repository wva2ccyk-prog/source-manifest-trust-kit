// State
let currentStage = 1;
let loadedIssueId = null;
let loadedFileName = null;
let loadedCandidatesData = null;
let loadedAcquisitionData = null;
let manualEdits = {}; // key: `idx-field`, value: boolean

// Helper to escape HTML for XSS prevention (fallback/safety)
function escapeHTML(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function safeHttpUrl(value) {
  try {
    const url = new URL(String(value || '').trim());
    if (url.protocol === 'http:' || url.protocol === 'https:') {
      return url.href;
    }
  } catch (_) {
    return null;
  }
  return null;
}

// UI Elements
const panels = document.querySelectorAll('.panel');
const steps = document.querySelectorAll('.stage-step');
const cliSteps = document.querySelectorAll('.cli-step');
const cliContent = document.getElementById('cli-content');

// Helper to switch stages
function setStage(stage) {
  currentStage = stage;

  // Update panels
  panels.forEach(p => p.classList.remove('active'));

  // Update rail
  steps.forEach(s => {
    const sNum = parseInt(s.dataset.stage);
    s.classList.remove('active', 'completed');
    if (sNum < stage) s.classList.add('completed');
    if (sNum === stage) s.classList.add('active');
  });

  // Activate specific panels based on stage
  if (stage === 1) document.getElementById('panel-upload-candidate').classList.add('active');
  if (stage === 2) document.getElementById('panel-candidate-selection').classList.add('active');
  if (stage === 3) document.getElementById('panel-upload-acquisition').classList.add('active');
  if (stage === 4) document.getElementById('panel-acquisition-review').classList.add('active');
  if (stage === 5) document.getElementById('panel-upload-package').classList.add('active');
  if (stage === 6) document.getElementById('panel-package-viewer').classList.add('active');

  // Update Checklist Visuals
  for (let i = 1; i <= 6; i++) {
    const item = document.getElementById(`check-step-${i}`);
    if (item) {
      if (i < stage) {
        item.classList.add('done');
      } else {
        item.classList.remove('done');
      }
    }
  }

  updateCliGuidance(stage);
  saveSession();
}

// Helper to update CLI sidebar
function updateCliGuidance(stage) {
  cliContent.innerHTML = '';

  let html = '';
  if (stage === 1) {
    const activeFile = loadedFileName || 'search_candidates.json';
    html = `
      <div class="cli-step active">
        <h4>1. Validate Candidate Artifact</h4>
        <div class="code-block">
          <pre><code id="cmd-1">python -m source_manifest_kit search-candidates-validate --artifact ./workspace/${escapeHTML(activeFile)}</code></pre>
          <button class="copy-btn" onclick="copyCmd('cmd-1')">Copy</button>
        </div>
        <p class="cli-help">Upload your <code>${escapeHTML(activeFile)}</code> to the left to continue.</p>
      </div>
    `;
  } else if (stage === 2) {
    const activeFile = loadedFileName || 'search_candidates.json';
    html = `
      <div class="cli-step active">
        <h4>2. Generate Selection</h4>
        <p class="cli-help">Select candidates, fill metadata, and click Confirm to generate your selection JSON.</p>
      </div>
      <div class="cli-step active" style="margin-top:24px;">
        <h4>3. Create Acquisition Manifest</h4>
        <div class="code-block">
          <pre><code id="cmd-2">python -m source_manifest_kit search-candidates-select --artifact ./workspace/${escapeHTML(activeFile)} --selection ./workspace/search_candidate_selection.json --output ./workspace/selected_acquisition_manifest.json</code></pre>
          <button class="copy-btn" onclick="copyCmd('cmd-2')">Copy</button>
        </div>
        <p class="cli-help">Run this after downloading your selection JSON.</p>
      </div>
    `;
  } else if (stage === 3) {
    html = `
      <div class="cli-step active">
        <h4>4. Fetch Direct URLs</h4>
        <div class="code-block">
          <pre><code id="cmd-3">python -m source_manifest_kit acquisition-fetch --manifest ./workspace/selected_acquisition_manifest.json --output-root ./workspace/acquired</code></pre>
          <button class="copy-btn" onclick="copyCmd('cmd-3')">Copy</button>
        </div>
        <p class="cli-help">Run this command, then upload the generated <code>acquisition_log.json</code> to review.</p>
      </div>
    `;
  } else if (stage === 4) {
    const activeFile = loadedFileName || 'acquisition_log.json';
    html = `
      <div class="cli-step active">
        <h4>5. Convert to Analysis Manifest</h4>
        <p class="cli-help">Confirm your review of the acquired sources on the left to unlock the conversion command.</p>
        <div class="code-block" style="opacity:0.5;" id="cmd-4-container">
          <pre><code id="cmd-4">python -m source_manifest_kit acquisition-to-analysis-manifest --acquisition-log ./workspace/acquired/${escapeHTML(activeFile)} --output ./workspace/analysis_sources.json --confirm-reviewed</code></pre>
          <button class="copy-btn" onclick="copyCmd('cmd-4')" id="cmd-4-btn" disabled>Copy</button>
        </div>
      </div>
    `;
  } else if (stage === 5) {
    html = `
      <div class="cli-step active">
        <h4>6. Run Analysis Package</h4>
        <div class="code-block">
          <pre><code id="cmd-5">python -m source_manifest_kit analysis-package --source-manifest ./workspace/analysis_sources.json --output-root ./workspace/package_out --excluded-detail-mode detailed</code></pre>
          <button class="copy-btn" onclick="copyCmd('cmd-5')">Copy</button>
        </div>
        <p class="cli-help">Upload the <code>final_operator_package.md</code> once analysis completes.</p>
      </div>
    `;
  } else if (stage === 6) {
    html = `
      <div class="cli-step active">
        <h4>Workflow Complete</h4>
        <p class="cli-help">Review the final operator package.</p>
      </div>
    `;
  }

  cliContent.innerHTML = html;
}

function copyCmd(id) {
  const code = document.getElementById(id).innerText;
  navigator.clipboard.writeText(code).then(() => {
    // Optional feedback
  });
}

// Stage 1: File Upload Candidates
const dropZoneCandidates = document.getElementById('drop-zone-candidates');
const fileInputCandidates = document.getElementById('file-input-candidates');

function handleCandidateFile(file) {
  loadedFileName = file.name;
  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      const data = JSON.parse(e.target.result);
      if (!data.candidates || !data.issue_id) throw new Error("Invalid format: missing candidates or issue_id");
      loadedIssueId = data.issue_id;
      loadedCandidatesData = data;
      manualEdits = {}; // reset manual edits
      renderCandidates(data);
      updateArtifactStatePanel();
      setStage(2);
    } catch (err) {
      alert("Error parsing candidate JSON: " + err.message);
    }
  };
  reader.readAsText(file);
}

if (fileInputCandidates) {
  fileInputCandidates.addEventListener('change', (e) => {
    if (e.target.files.length > 0) handleCandidateFile(e.target.files[0]);
  });
}

// Drag & Drop
if (dropZoneCandidates) {
  ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(ev => {
    dropZoneCandidates.addEventListener(ev, preventDefaults, false);
  });
  ['dragenter', 'dragover'].forEach(ev => {
    dropZoneCandidates.addEventListener(ev, () => dropZoneCandidates.classList.add('dragover'), false);
  });
  ['dragleave', 'drop'].forEach(ev => {
    dropZoneCandidates.addEventListener(ev, () => dropZoneCandidates.classList.remove('dragover'), false);
  });
  dropZoneCandidates.addEventListener('drop', (e) => {
    if (e.dataTransfer.files.length > 0) handleCandidateFile(e.dataTransfer.files[0]);
  });
}
function preventDefaults(e) { e.preventDefault(); e.stopPropagation(); }

// Heuristic suggestions for source metadata
function getSuggestions(cand, idx) {
  const title = cand.title || cand.candidate_id;
  const nameSuggest = title.toLowerCase()
    .replace(/[^a-z0-9_]/g, '_')
    .replace(/__+/g, '_')
    .replace(/^_+|_+$/g, '') || `source_${idx}`;

  let typeSuggest = 'official';
  const textToScan = ((cand.title || '') + ' ' + (cand.url || '') + ' ' + (cand.publisher || '') + ' ' + (cand.candidate_id || '') + ' ' + (cand.warnings ? cand.warnings.join(' ') : '')).toLowerCase();

  if (textToScan.includes('news') || textToScan.includes('press') || textToScan.includes('reuters') || textToScan.includes('bloomberg') || textToScan.includes('journal')) {
    typeSuggest = 'news';
  } else if (textToScan.includes('forum') || textToScan.includes('reddit') || textToScan.includes('twitter') || textToScan.includes('discord') || textToScan.includes('telegram')) {
    typeSuggest = 'social';
  } else if (textToScan.includes('analyst') || textToScan.includes('research') || textToScan.includes('report')) {
    typeSuggest = 'analyst';
  } else if (textToScan.includes('community') || textToScan.includes('blog')) {
    typeSuggest = 'community';
  } else if (textToScan.includes('note') || textToScan.includes('memo')) {
    typeSuggest = 'user_note';
  } else if (textToScan.includes('company') || textToScan.includes('corporate') || textToScan.includes('investor')) {
    typeSuggest = 'company';
  }

  let modeSuggest = 'general';
  if (textToScan.includes('finance') || textToScan.includes('stock') || textToScan.includes('crypto')) {
    modeSuggest = 'finance';
  }

  return { nameSuggest, typeSuggest, modeSuggest };
}

// Stage 2: Render Candidates & Selection Logic
function renderCandidates(data) {
  const metaContainer = document.getElementById('candidate-meta-info');
  metaContainer.textContent = ''; // clear

  const buildMeta = (label, value) => {
    const b = document.createElement('strong');
    b.textContent = label + ': ';
    const span = document.createElement('span');
    span.textContent = value;
    metaContainer.appendChild(b);
    metaContainer.appendChild(span);
    metaContainer.appendChild(document.createElement('br'));
  };

  buildMeta('Issue ID', data.issue_id);
  buildMeta('Query', data.query);
  buildMeta('Provider', data.provider);

  const container = document.getElementById('candidates-container');
  container.innerHTML = '';

  // Get session state for values
  let sessionMeta = null;
  const sessionRaw = localStorage.getItem('trust_os_session');
  if (sessionRaw) {
    try {
      const sess = JSON.parse(sessionRaw);
      sessionMeta = sess.selectedMetadata;
    } catch(e){}
  }

  data.candidates.forEach((cand, idx) => {
    const card = document.createElement('div');
    card.className = 'candidate-card';

    // Build candidate-header
    const header = document.createElement('div');
    header.className = 'candidate-header';
    const label = document.createElement('label');
    label.className = 'checkbox-container';

    const input = document.createElement('input');
    input.type = 'checkbox';
    input.className = 'candidate-select';
    input.dataset.id = cand.candidate_id;
    input.id = `chk-${idx}`;

    const span = document.createElement('span');
    span.className = 'checkmark';

    const titleText = document.createTextNode(' ' + (cand.title || cand.candidate_id));

    label.appendChild(input);
    label.appendChild(span);
    label.appendChild(titleText);
    header.appendChild(label);

    // Build candidate-details
    const details = document.createElement('div');
    details.className = 'candidate-details';

    const safeCandidateUrl = safeHttpUrl(cand.url);
    if (safeCandidateUrl) {
      const urlA = document.createElement('a');
      urlA.href = safeCandidateUrl;
      urlA.target = '_blank';
      urlA.rel = 'noopener noreferrer';
      urlA.className = 'candidate-url';
      urlA.textContent = cand.url;
      details.appendChild(urlA);
    } else {
      const urlText = document.createElement('span');
      urlText.className = 'candidate-url unsafe-url';
      urlText.textContent = cand.url || 'N/A';
      details.appendChild(urlText);
    }

    const noteDiv = document.createElement('div');
    noteDiv.style = 'font-size: 0.75rem; color: var(--text-muted); margin-bottom: 8px;';
    const emNote = document.createElement('em');
    emNote.textContent = 'Note: Candidate presence is not verification. Opening a URL is outside deterministic analysis.';
    noteDiv.appendChild(emNote);
    details.appendChild(noteDiv);

    // Warnings
    if (cand.warnings && Array.isArray(cand.warnings)) {
      const wDiv = document.createElement('div');
      wDiv.className = 'alert alert-warning';
      wDiv.style = 'padding:8px; margin:8px 0;';
      cand.warnings.forEach((w, wIdx) => {
        const textNode = document.createTextNode(w);
        wDiv.appendChild(textNode);
        if (wIdx < cand.warnings.length - 1) wDiv.appendChild(document.createElement('br'));
      });
      details.appendChild(wDiv);
    }

    // Metadata form (static HTML template for structure)
    const metaForm = document.createElement('div');
    metaForm.className = 'candidate-metadata-form';
    metaForm.innerHTML = `
      <div class="form-group">
        <label>Source Name <span class="suggest-badge" id="badge-name-${idx}"></span></label>
        <input type="text" class="meta-source-name" placeholder="e.g. selected_forum_1" id="name-${idx}">
      </div>
      <div class="form-group">
        <label>Source Type <span class="suggest-badge" id="badge-type-${idx}"></span></label>
        <select class="meta-source-type" id="type-${idx}">
          <option value="official">Official</option>
          <option value="company">Company</option>
          <option value="news">News</option>
          <option value="analyst">Analyst</option>
          <option value="community">Community</option>
          <option value="social">Social</option>
          <option value="user_note">User Note</option>
          <option value="unknown">Unknown</option>
        </select>
      </div>
      <div class="form-group">
        <label>Mode <span class="suggest-badge" id="badge-mode-${idx}"></span></label>
        <select class="meta-mode" id="mode-${idx}">
          <option value="general">General</option>
          <option value="finance">Finance</option>
        </select>
      </div>
    `;
    details.appendChild(metaForm);

    card.appendChild(header);
    card.appendChild(details);

    // Get suggestions
    const suggestions = getSuggestions(cand, idx);
    const nameInput = metaForm.querySelector('.meta-source-name');
    const typeSelect = metaForm.querySelector('.meta-source-type');
    const modeSelect = metaForm.querySelector('.meta-mode');

    // Retrieve saved state if present
    const saved = sessionMeta ? sessionMeta.find(m => m.candidate_id === cand.candidate_id) : null;
    const valName = saved ? saved.source_name : suggestions.nameSuggest;
    const valType = saved ? saved.source_type : suggestions.typeSuggest;
    const valMode = saved ? saved.mode : suggestions.modeSuggest;

    nameInput.value = valName;
    typeSelect.value = valType;
    modeSelect.value = valMode;

    if (saved && saved.checked) {
      input.checked = true;
      card.classList.add('selected');
    }

    // Badge logic
    const updateBadge = (field, inputEl, suggestedVal) => {
      const badge = metaForm.querySelector(`#badge-${field}-${idx}`);
      const isManualKey = `${idx}-${field}`;
      const isManual = manualEdits[isManualKey] || (inputEl.value !== suggestedVal);
      if (isManual) {
        manualEdits[isManualKey] = true;
        badge.className = 'suggest-badge manual';
        badge.textContent = 'edited';
      } else {
        badge.className = 'suggest-badge auto';
        badge.textContent = 'suggested';
      }
    };

    updateBadge('name', nameInput, suggestions.nameSuggest);
    updateBadge('type', typeSelect, suggestions.typeSuggest);
    updateBadge('mode', modeSelect, suggestions.modeSuggest);

    // Live suggestion edited tracker
    nameInput.addEventListener('input', () => {
      manualEdits[`${idx}-name`] = true;
      updateBadge('name', nameInput, suggestions.nameSuggest);
      saveSession();
    });
    typeSelect.addEventListener('change', () => {
      manualEdits[`${idx}-type`] = true;
      updateBadge('type', typeSelect, suggestions.typeSuggest);
      saveSession();
    });
    modeSelect.addEventListener('change', () => {
      manualEdits[`${idx}-mode`] = true;
      updateBadge('mode', modeSelect, suggestions.modeSuggest);
      saveSession();
    });

    // Toggle form opacity when checked
    input.addEventListener('change', (e) => {
      if(e.target.checked) card.classList.add('selected');
      else card.classList.remove('selected');
      saveSession();
    });

    container.appendChild(card);
  });
}

// Stage 2 Ergonomic Controls Action listeners
const btnSelectAll = document.getElementById('btn-select-all');
if (btnSelectAll) {
  btnSelectAll.addEventListener('click', () => {
    const cards = document.querySelectorAll('.candidate-card');
    cards.forEach(card => {
      const chk = card.querySelector('.candidate-select');
      if (chk) {
        chk.checked = true;
        card.classList.add('selected');
      }
    });
    saveSession();
  });
}

const btnClearAll = document.getElementById('btn-clear-all');
if (btnClearAll) {
  btnClearAll.addEventListener('click', () => {
    const cards = document.querySelectorAll('.candidate-card');
    cards.forEach(card => {
      const chk = card.querySelector('.candidate-select');
      if (chk) {
        chk.checked = false;
        card.classList.remove('selected');
      }
    });
    saveSession();
  });
}

// Import selection file
const fileImportSelection = document.getElementById('file-import-selection');
if (fileImportSelection) {
  fileImportSelection.addEventListener('change', (e) => {
    if (e.target.files.length > 0) handleSelectionImportFile(e.target.files[0]);
  });
}

function handleSelectionImportFile(file) {
  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      const data = JSON.parse(e.target.result);
      if (!data.selected_candidates || !Array.isArray(data.selected_candidates)) {
        throw new Error("Invalid format: missing selected_candidates array");
      }

      // Restore based on selection
      const sessionMetadata = [];
      const cards = document.querySelectorAll('.candidate-card');
      cards.forEach((card, idx) => {
        const chk = card.querySelector('.candidate-select');
        const cId = chk.dataset.id;

        const imported = data.selected_candidates.find(sc => sc.candidate_id === cId);
        if (imported) {
          sessionMetadata.push({
            idx: idx.toString(),
            candidate_id: cId,
            source_name: imported.source_name,
            source_type: imported.source_type,
            mode: imported.mode,
            checked: true
          });
        }
      });

      // Temporarily overwrite localStorage and re-render
      const raw = localStorage.getItem('trust_os_session');
      if (raw) {
        const sess = JSON.parse(raw);
        sess.selectedMetadata = sessionMetadata;
        localStorage.setItem('trust_os_session', JSON.stringify(sess));
      }

      renderCandidates(loadedCandidatesData);
      saveSession();
      alert("Successfully imported selection JSON.");
    } catch (err) {
      alert("Error importing selection JSON: " + err.message);
    }
  };
  reader.readAsText(file);
}

document.getElementById('btn-generate-selection').addEventListener('click', () => {
  const selectedBoxes = document.querySelectorAll('.candidate-select:checked');
  if (selectedBoxes.length === 0) {
    alert("Please select at least one candidate.");
    return;
  }

  const selected_candidates = [];
  let hasError = false;

  selectedBoxes.forEach(chk => {
    const card = chk.closest('.candidate-card');
    const cId = chk.dataset.id;
    const sName = card.querySelector('.meta-source-name').value.trim();
    const sType = card.querySelector('.meta-source-type').value;
    const sMode = card.querySelector('.meta-mode').value;

    if (!sName) {
      alert("Source Name is required for selected candidates.");
      hasError = true;
      return;
    }

    selected_candidates.push({
      candidate_id: cId,
      source_name: sName,
      source_type: sType,
      mode: sMode
    });
  });

  if (hasError) return;

  const analysisReq = document.getElementById('analysis-request').value.trim();

  const selectionJson = {
    issue_id: loadedIssueId,
    confirm_reviewed: true,
    analysis_request: analysisReq || undefined,
    selected_candidates: selected_candidates
  };

  // Download logic
  const blob = new Blob([JSON.stringify(selectionJson, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'search_candidate_selection.json';
  a.click();
  URL.revokeObjectURL(url);

  // Move to next stage
  setStage(3);
});

// Stage 3: Acquisition Log Upload
const fileInputAcq = document.getElementById('file-input-acquisition');
if (fileInputAcq) {
  fileInputAcq.addEventListener('change', (e) => {
    if (e.target.files.length > 0) handleAcqFile(e.target.files[0]);
  });
}

function handleAcqFile(file) {
  loadedFileName = file.name;
  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      const data = JSON.parse(e.target.result);
      loadedAcquisitionData = data;

      // Rule 6: Issue continuity check
      if (data.issue_id) {
        if (data.issue_id !== loadedIssueId) {
          if (!confirm(`Warning: The uploaded acquisition log issue ID (${escapeHTML(data.issue_id)}) does not match the loaded candidate issue ID (${escapeHTML(loadedIssueId)}).\n\nDo you want to proceed anyway?`)) {
            return;
          }
        }
      } else {
        if (!confirm(`Caution: The uploaded acquisition log has no issue_id. We cannot verify continuity.\n\nDo you want to proceed anyway?`)) {
          return;
        }
      }

      renderAcquisitionReview(data);
      updateArtifactStatePanel();
      setStage(4);
    } catch (err) {
      alert("Error parsing acquisition log: " + err.message);
    }
  };
  reader.readAsText(file);
}

function renderAcquisitionReview(data) {
  const container = document.getElementById('acquisition-container');
  container.textContent = ''; // clear

  const attemptedCount = data.attempted || (data.records ? data.records.length : (data.results ? Object.keys(data.results).length : 0));
  const successCount = data.success_count || (data.records ? data.records.filter(r => r.status === 'fetched').length : 0);
  const warningCount = data.records ? data.records.filter(r => r.warnings && r.warnings.length > 0).length : 0;
  const nonFetchedCount = attemptedCount - successCount;

  // Render triage summary chips
  const countAll = document.getElementById('count-all');
  const countFetched = document.getElementById('count-fetched');
  const countWarning = document.getElementById('count-warning');
  const countNonFetched = document.getElementById('count-non-fetched');

  if (countAll) countAll.textContent = attemptedCount;
  if (countFetched) countFetched.textContent = successCount;
  if (countWarning) countWarning.textContent = warningCount;
  if (countNonFetched) countNonFetched.textContent = nonFetchedCount;

  const summaryAlert = document.createElement('div');
  summaryAlert.className = 'alert alert-warning';

  const b1 = document.createElement('strong');
  b1.textContent = 'Total Attempted: ';
  const s1 = document.createTextNode(attemptedCount);
  const br = document.createElement('br');
  const b2 = document.createElement('strong');
  b2.textContent = 'Successful: ';
  const s2 = document.createTextNode(successCount);

  summaryAlert.appendChild(b1);
  summaryAlert.appendChild(s1);
  summaryAlert.appendChild(br);
  summaryAlert.appendChild(b2);
  summaryAlert.appendChild(s2);

  container.appendChild(summaryAlert);

  if (data.records && Array.isArray(data.records)) {
    const noteDiv = document.createElement('div');
    noteDiv.style = 'font-size: 0.75rem; color: var(--text-muted); margin-bottom: 8px;';
    const emNote = document.createElement('em');
    emNote.textContent = 'Note: Opening URLs is outside deterministic analysis.';
    noteDiv.appendChild(emNote);
    container.appendChild(noteDiv);

    const table = document.createElement('table');
    table.style = 'width:100%; text-align:left; border-collapse:collapse; margin-top:16px; font-size: 0.85rem;';
    table.innerHTML = `
      <thead>
        <tr style="border-bottom: 1px solid var(--border-color);">
          <th style="padding:8px;">Source Name</th>
          <th style="padding:8px;">URL</th>
          <th style="padding:8px;">Status</th>
          <th style="padding:8px;">Warnings</th>
        </tr>
      </thead>
      <tbody></tbody>
    `;
    const tbody = table.querySelector('tbody');

    data.records.forEach(r => {
      const tr = document.createElement('tr');
      tr.style = 'border-bottom: 1px solid var(--glass-border);';
      tr.dataset.status = r.status || 'unknown';
      tr.dataset.warnings = (r.warnings && r.warnings.length > 0) ? 'true' : 'false';

      const tdName = document.createElement('td');
      tdName.style = 'padding:8px;';
      tdName.textContent = r.source_name || 'N/A';
      tr.appendChild(tdName);

      const tdUrl = document.createElement('td');
      tdUrl.style = 'padding:8px; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;';
      const url = r.source_url || r.url || 'N/A';
      const safeUrl = safeHttpUrl(url);
      if (safeUrl) {
        const aUrl = document.createElement('a');
        aUrl.href = safeUrl;
        aUrl.target = '_blank';
        aUrl.rel = 'noopener noreferrer';
        aUrl.style = 'color: var(--text-muted); text-decoration: underline;';
        aUrl.title = url;
        aUrl.textContent = url;
        tdUrl.appendChild(aUrl);
      } else {
        tdUrl.textContent = url;
      }
      tr.appendChild(tdUrl);

      const tdStatus = document.createElement('td');
      tdStatus.style = 'padding:8px;';
      const statusSpan = document.createElement('span');
      const statusColor = r.status === 'fetched' ? 'var(--success)' : 'var(--danger)';
      statusSpan.style = `padding:4px 8px; border-radius:4px; background: ${statusColor}; color:#fff;`;
      statusSpan.textContent = r.status || 'unknown';
      tdStatus.appendChild(statusSpan);
      tr.appendChild(tdStatus);

      const tdWarnings = document.createElement('td');
      tdWarnings.style = 'padding:8px; color: var(--warning);';
      if (r.warnings && Array.isArray(r.warnings)) {
        r.warnings.forEach((w, wIdx) => {
          tdWarnings.appendChild(document.createTextNode(w));
          if (wIdx < r.warnings.length - 1) tdWarnings.appendChild(document.createElement('br'));
        });
      }
      tr.appendChild(tdWarnings);

      tbody.appendChild(tr);
    });
    container.appendChild(table);
  }
}

// Stage 4 filters triage event listeners
const filterChips = document.querySelectorAll('.filter-chip');
filterChips.forEach(chip => {
  chip.addEventListener('click', (e) => {
    filterChips.forEach(c => c.classList.remove('active'));
    const activeChip = e.currentTarget;
    activeChip.classList.add('active');

    const filter = activeChip.dataset.filter;
    const rows = document.querySelectorAll('.acquisition-list table tbody tr');
    rows.forEach(row => {
      const status = row.dataset.status;
      const hasWarnings = row.dataset.warnings === 'true';

      if (filter === 'all') {
        row.style.display = '';
      } else if (filter === 'fetched') {
        row.style.display = status === 'fetched' ? '' : 'none';
      } else if (filter === 'warning') {
        row.style.display = hasWarnings ? '' : 'none';
      } else if (filter === 'non-fetched') {
        row.style.display = status !== 'fetched' ? '' : 'none';
      }
    });
  });
});

document.getElementById('gate-acquire-confirm').addEventListener('change', (e) => {
  const btn = document.getElementById('btn-generate-analysis-manifest');
  const cmdContainer = document.getElementById('cmd-4-container');
  const cmdBtn = document.getElementById('cmd-4-btn');

  if (e.target.checked) {
    btn.disabled = false;
    if(cmdContainer) cmdContainer.style.opacity = '1';
    if(cmdBtn) cmdBtn.disabled = false;
  } else {
    btn.disabled = true;
    if(cmdContainer) cmdContainer.style.opacity = '0.5';
    if(cmdBtn) cmdBtn.disabled = true;
  }
});

document.getElementById('btn-generate-analysis-manifest').addEventListener('click', () => {
  setStage(5);
});

// Stage 5: Package Upload
const fileInputPkg = document.getElementById('file-input-package');
if (fileInputPkg) {
  fileInputPkg.addEventListener('change', (e) => {
    if (e.target.files.length > 0) handlePkgFile(e.target.files[0]);
  });
}

function handlePkgFile(file) {
  const reader = new FileReader();
  reader.onload = (e) => {
    const markdownText = e.target.result;

    // Rule 6: Issue continuity check
    if (loadedIssueId) {
      const escapedIssueId = loadedIssueId.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&');
      const issueIdRegex = new RegExp(escapedIssueId, 'i');
      if (!issueIdRegex.test(markdownText)) {
        if (!confirm(`Warning: The uploaded final operator package does not contain the loaded issue ID (${escapeHTML(loadedIssueId)}). Continuity cannot be verified.\n\nDo you want to proceed anyway?`)) {
          return;
        }
      }
    } else {
      if (!confirm(`Caution: No active issue ID is loaded. Continuity cannot be verified.\n\nDo you want to proceed anyway?`)) {
        return;
      }
    }

    renderPackage(markdownText);
    setStage(6);
  };
  reader.readAsText(file);
}

// Stage 6 enhanced parsing/formatting
function extractMarkdownStats(text) {
  const stats = {
    issueId: loadedIssueId || 'N/A',
    sourceCount: 0,
    runCount: 0,
    riskBuckets: { low: 0, medium: 0, high: 0 },
    claimCounts: { other: 0 }
  };

  const issueMatch = text.match(/Issue ID\s*:\s*([^\n\r]+)/i);
  if (issueMatch) stats.issueId = issueMatch[1].trim();

  const srcMatch = text.match(/(?:Source Count|Sources|Total Sources)\s*:\s*(\d+)/i);
  if (srcMatch) {
    stats.sourceCount = parseInt(srcMatch[1]);
  } else {
    const matches = text.match(/^[-\*]\s+\[.*?\]\(.*?\)/gm);
    if (matches) stats.sourceCount = matches.length;
  }

  const runs = text.match(/Analysis Run\s*#?\s*(\d+)/gi);
  if (runs) stats.runCount = runs.length;

  const lowRisk = text.match(/low[- ]risk/gi);
  const medRisk = text.match(/medium[- ]risk|med[- ]risk/gi);
  const highRisk = text.match(/high[- ]risk/gi);
  if (lowRisk) stats.riskBuckets.low = lowRisk.length;
  if (medRisk) stats.riskBuckets.medium = medRisk.length;
  if (highRisk) stats.riskBuckets.high = highRisk.length;

  const claims = text.match(/claim/gi);
  if (claims) stats.claimCounts.other = claims.length;

  return stats;
}

function renderPackageSummaryHeader(stats) {
  const header = document.getElementById('package-summary-header');
  if (!header) return;
  header.textContent = ''; // clear

  const createCard = (val, label) => {
    const card = document.createElement('div');
    card.className = 'pkg-summary-card';
    const valueEl = document.createElement('div');
    valueEl.className = 'value';
    valueEl.textContent = val;
    const labelEl = document.createElement('div');
    labelEl.className = 'label';
    labelEl.textContent = label;
    card.appendChild(valueEl);
    card.appendChild(labelEl);
    header.appendChild(card);
  };

  createCard(stats.issueId, 'Issue ID');
  if (stats.sourceCount > 0) createCard(stats.sourceCount, 'Sources Analyzed');
  createCard(stats.runCount || '1', 'Analysis Runs');

  const riskStr = `L: ${stats.riskBuckets.low} | M: ${stats.riskBuckets.medium} | H: ${stats.riskBuckets.high}`;
  createCard(riskStr, 'Risk Contexts');

  if (stats.claimCounts.other > 0) {
    createCard(stats.claimCounts.other, 'Claims Flagged');
  }
}

function renderPackage(markdownText) {
  const container = document.getElementById('package-content');
  const stats = extractMarkdownStats(markdownText);
  renderPackageSummaryHeader(stats);

  // Monospace/chip conversion for paths (without messing up URL schemas like http://)
  let enhancedMd = markdownText;
  enhancedMd = enhancedMd.replace(/(\b[a-zA-Z]:\\[^\s\)]+|(?:\.\/|\.\.\\)[^\s\)]+\.(?:json|md|txt|csv|py))\b/g, (match) => {
    return `<span class="path-chip">${escapeHTML(match)}</span>`;
  });

  // Highlight [excluded-unsafe-finance-claim]
  enhancedMd = enhancedMd.replace(/\[excluded-unsafe-finance-claim\]/gi, `<span class="masked-placeholder">[excluded-unsafe-finance-claim]</span>`);

  if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
    let html = marked.parse(enhancedMd);
    html = DOMPurify.sanitize(html);

    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = html;

    // Nest under Collapsible Details tag
    const collapsibleHeaders = [
      "Excluded Finance Summary",
      "Unresolved Claims",
      "Verification Request Packet",
      "Source Conflict Summary",
      "Operator Checklist",
      "Known Limitations"
    ];

    collapsibleHeaders.forEach(headerText => {
      const headers = Array.from(tempDiv.querySelectorAll('h1, h2, h3, h4, h5, h6'));
      const targetHeader = headers.find(h => h.textContent.trim().toLowerCase().includes(headerText.toLowerCase()));
      if (targetHeader) {
        const details = document.createElement('details');
        const summary = document.createElement('summary');
        summary.textContent = targetHeader.textContent;
        details.appendChild(summary);

        const contentDiv = document.createElement('div');
        contentDiv.className = 'details-content';

        let sibling = targetHeader.nextSibling;
        const targetLevel = parseInt(targetHeader.tagName.substring(1));
        const siblingsToMove = [];

        while (sibling) {
          if (sibling.nodeType === Node.ELEMENT_NODE && sibling.tagName.match(/^H[1-6]$/)) {
            const currentLevel = parseInt(sibling.tagName.substring(1));
            if (currentLevel <= targetLevel) {
              break;
            }
          }
          siblingsToMove.push(sibling);
          sibling = sibling.nextSibling;
        }

        siblingsToMove.forEach(sib => contentDiv.appendChild(sib));
        details.appendChild(contentDiv);

        targetHeader.parentNode.replaceChild(details, targetHeader);
      }
    });

    // Jump List Links
    const jumpList = document.getElementById('package-jump-list');
    if (jumpList) {
      const headers = Array.from(tempDiv.querySelectorAll('h1, h2, h3, h4, h5, h6, summary'));
      if (headers.length > 0) {
        jumpList.style.display = 'block';
        jumpList.textContent = ''; // clear

        const jumpTitle = document.createElement('h4');
        jumpTitle.textContent = 'Jump to Section:';
        jumpList.appendChild(jumpTitle);

        const linksDiv = document.createElement('div');
        linksDiv.className = 'jump-links';

        headers.forEach((h, hIdx) => {
          const text = h.textContent.trim();
          if (text.length > 0) {
            const id = `heading-${hIdx}`;
            h.id = id;

            const a = document.createElement('a');
            a.className = 'jump-link';
            a.href = `#${id}`;
            a.textContent = text;

            if (h.tagName === 'SUMMARY') {
              a.addEventListener('click', (e) => {
                e.preventDefault();
                const detailsEl = h.closest('details');
                if (detailsEl) detailsEl.open = true;
                h.scrollIntoView({ behavior: 'smooth' });
              });
            }
            linksDiv.appendChild(a);
          }
        });
        jumpList.appendChild(linksDiv);
      } else {
        jumpList.style.display = 'none';
      }
    }

    container.textContent = '';
    container.appendChild(tempDiv);
  } else {
    container.innerHTML = `<pre>${escapeHTML(markdownText)}</pre>`;
  }
}

// Artifact State Panel update helper
function updateArtifactStatePanel() {
  const panel = document.getElementById('artifact-state-panel');
  if (!panel) return;
  if (!loadedFileName) {
    panel.style.display = 'none';
    return;
  }
  panel.style.display = 'block';
  panel.textContent = '';

  const title = document.createElement('div');
  title.style = 'font-weight: bold; border-bottom: 1px solid var(--border-color); padding-bottom: 4px; margin-bottom: 6px;';
  title.textContent = 'Active Artifact';
  panel.appendChild(title);

  const fileDiv = document.createElement('div');
  fileDiv.innerHTML = `<strong>File:</strong> ${escapeHTML(loadedFileName)}`;
  panel.appendChild(fileDiv);

  if (loadedIssueId) {
    const issueDiv = document.createElement('div');
    issueDiv.innerHTML = `<strong>Issue ID:</strong> ${escapeHTML(loadedIssueId)}`;
    panel.appendChild(issueDiv);
  }

  if (loadedCandidatesData && loadedCandidatesData.candidates) {
    const countDiv = document.createElement('div');
    countDiv.innerHTML = `<strong>Candidates:</strong> ${loadedCandidatesData.candidates.length}`;
    panel.appendChild(countDiv);
  } else if (loadedAcquisitionData && loadedAcquisitionData.records) {
    const countDiv = document.createElement('div');
    countDiv.innerHTML = `<strong>Acquired Records:</strong> ${loadedAcquisitionData.records.length}`;
    panel.appendChild(countDiv);
  }
}

// Session Management LocalStorage
function saveSession() {
  const sessionState = {
    currentStage,
    loadedIssueId,
    loadedFileName,
    manualEdits,
    selectedMetadata: []
  };

  const selectedBoxes = document.querySelectorAll('.candidate-select:checked');
  selectedBoxes.forEach(chk => {
    const card = chk.closest('.candidate-card');
    const cId = chk.dataset.id;
    const sName = card.querySelector('.meta-source-name').value.trim();
    const sType = card.querySelector('.meta-source-type').value;
    const sMode = card.querySelector('.meta-mode').value;
    const idx = chk.id.split('-')[1];

    sessionState.selectedMetadata.push({
      idx,
      candidate_id: cId,
      source_name: sName,
      source_type: sType,
      mode: sMode,
      checked: true
    });
  });

  const allCards = document.querySelectorAll('.candidate-card');
  allCards.forEach((card, idx) => {
    const chk = card.querySelector('.candidate-select');
    if (chk && !chk.checked) {
      const sName = card.querySelector('.meta-source-name').value.trim();
      const sType = card.querySelector('.meta-source-type').value;
      const sMode = card.querySelector('.meta-mode').value;
      if (sName || sType !== 'official' || sMode !== 'general') {
        sessionState.selectedMetadata.push({
          idx: idx.toString(),
          candidate_id: chk.dataset.id,
          source_name: sName,
          source_type: sType,
          mode: sMode,
          checked: false
        });
      }
    }
  });

  localStorage.setItem('trust_os_session', JSON.stringify(sessionState));
}

function restoreSession() {
  const raw = localStorage.getItem('trust_os_session');
  if (!raw) return;
  try {
    const state = JSON.parse(raw);
    if (!state.currentStage) return;

    currentStage = state.currentStage;
    loadedIssueId = state.loadedIssueId;
    loadedFileName = state.loadedFileName;
    manualEdits = state.manualEdits || {};

    updateArtifactStatePanel();

    if (currentStage > 1) {
      setStage(currentStage);

      const alertContainer = document.querySelector('.workspace-area');
      if (alertContainer) {
        const notice = document.createElement('div');
        notice.className = 'alert alert-warning';
        notice.style = 'margin-bottom: 16px; font-size: 0.85rem;';
        const fileHint = loadedFileName ? `<code>${escapeHTML(loadedFileName)}</code>` : 'your artifact file';
        notice.innerHTML = `<strong>Session restored to Stage ${currentStage}.</strong> File contents are not persisted for safety. Please re-upload ${fileHint} to resume fully.`;
        alertContainer.insertBefore(notice, alertContainer.firstChild);
      }
    }
  } catch (e) {
    console.error("Error restoring session:", e);
  }
}

// Reset Session Logic
document.getElementById('btn-reset-session').addEventListener('click', () => {
  if(confirm("Are you sure you want to reset the session? Unsaved progress will be lost.")) {
    loadedIssueId = null;
    loadedFileName = null;
    loadedCandidatesData = null;
    loadedAcquisitionData = null;
    manualEdits = {};

    localStorage.removeItem('trust_os_session');

    document.getElementById('candidates-container').innerHTML = '';
    document.getElementById('acquisition-container').innerHTML = '';
    document.getElementById('package-content').innerHTML = '';
    document.getElementById('candidate-meta-info').innerHTML = '';
    document.getElementById('analysis-request').value = '';

    // reset file inputs
    document.getElementById('file-input-candidates').value = '';
    document.getElementById('file-input-acquisition').value = '';
    document.getElementById('file-input-package').value = '';

    // reset gate
    document.getElementById('gate-acquire-confirm').checked = false;
    document.getElementById('btn-generate-analysis-manifest').disabled = true;
    const cmd4Container = document.getElementById('cmd-4-container');
    if(cmd4Container) cmd4Container.style.opacity = '0.5';
    const cmd4Btn = document.getElementById('cmd-4-btn');
    if(cmd4Btn) cmd4Btn.disabled = true;

    // Hide panels and jump lists
    const statePanel = document.getElementById('artifact-state-panel');
    if(statePanel) statePanel.style.display = 'none';
    const jumpList = document.getElementById('package-jump-list');
    if(jumpList) jumpList.style.display = 'none';
    const pkgHeader = document.getElementById('package-summary-header');
    if(pkgHeader) pkgHeader.innerHTML = '';

    setStage(1);
  }
});

// Initialize
restoreSession();
if (currentStage === 1) {
  setStage(1);
}
