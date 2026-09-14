const $ = id => document.getElementById(id);
const HOSTED = Boolean(LOCAL?.hosted);
function node(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = String(text);
  if (className) el.className = className;
  return el;
}
function tableRow(table, label, value) {
  const row = node('tr'); row.append(node('th', label), node('td', value)); table.append(row);
}
function download(value, name) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], {type:'application/json'}));
  const a = node('a'); a.href = url; a.download = name; document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
let verifying = false, selectedFile = null, generatedPackage = null, jobId = null, polling = false;
function workspaceMode(mode) {
  const generate = mode === 'generate';
  $('generate').hidden = !generate; $('verify').hidden = generate;
  $('show-generate').setAttribute('aria-pressed', String(generate));
  $('show-verify').setAttribute('aria-pressed', String(!generate));
  $('workspace-title').textContent = generate ? 'Generate a proof.' : 'Inspect a proof.';
  $('workspace-intro').textContent = generate ? (HOSTED ? 'Run a model on the hosted server. Export a proof of one calculation.' : 'Run a model locally. Export a proof of one calculation.') : 'Check a computation against registered model weights.';
}
function fileTypeLabel(m) {
  // GGUF file type 15 is LLAMA_FTYPE_MOSTLY_Q4_K_M in the pinned llama.h.
  return m.model.file_type === 15 ? 'Q4_K_M' : `GGUF type ${m.model.file_type}`;
}
function renderModels() {
  $('models-view').replaceChildren();
  const query = $('model-search').value.trim().toLowerCase();
  const models = DATA.manifests.filter(m => (m.model.name + ' ' + fileTypeLabel(m) + ' ' + m.model.file_sha256).toLowerCase().includes(query));
  const supported = DATA.manifests.filter(m => m.tensors.some(t => t.groth16)).length;
  $('catalog-summary').textContent = `${DATA.manifests.length} registered model files. ${supported} can be checked with proofs.`;
  if (!models.length) $('models-view').append(node('p', 'No registered models match your search.', 'small'));
  for (const m of models) {
    const record = node('details', undefined, 'model-record'), table = node('table');
    const committed = m.tensors.filter(t => t.groth16), groups = committed.reduce((n, t) => n + t.groth16.groups.length, 0);
    const summary = node('summary', undefined, 'model-summary');
    const identity = node('div', undefined, 'model-identity');
    identity.append(node('h3', m.model.name), node('p', fileTypeLabel(m) + ' · ' + m.model.file_sha256.slice(0,16) + '…', 'fingerprint'));
    const support = node('div', undefined, 'model-support');
    support.append(node('strong', committed.length ? `${committed.length} of ${m.tensors.length} tensors can be checked` : 'File fingerprint only'));
    support.append(node('p', committed.length ? `${groups.toLocaleString()} row groups, checked one at a time` : 'No proofs can be checked for this file yet'));
    support.append(node('p', DATA.local_generation?.includes(m.manifest_id) ? 'Can generate proofs in the local workspace' : 'Cannot generate proofs in the local workspace'));
    summary.append(identity, support, node('span', 'Details', 'record-link')); record.append(summary);
    const body = node('div', undefined, 'model-details');
    body.append(node('p', committed.length ? 'These registrations let the verifier check individual integer row groups. They do not prove a complete operation or model response.' : 'This exact model file is recorded. No proof support is registered for it yet.', 'small'));
    tableRow(table, 'Registration', m.manifest_id);
    tableRow(table, 'Model file SHA-256', m.model.file_sha256);
    tableRow(table, 'Execution metadata', `${m.execution.statement}; ${m.execution.backend}; ${m.execution.threads} threads. Full execution is not proven.`);
    tableRow(table, 'Trust', 'Registered by this project. Independent review is pending. The proving parameters come from an experimental single-contributor setup.');
    body.append(table);
    const button = node('button', 'Download registration', 'secondary');
    button.addEventListener('click', () => download(m, 'registration.json')); body.append(button);
    const details = node('details'), tensors = node('table'); details.append(node('summary', `Show all ${m.tensors.length} tensors`));
    for (const t of m.tensors) tableRow(tensors, t.name, `${t.type}; ${t.shape.join(' × ')}; ${t.groth16 ? t.groth16.groups.length + ' registered row groups' : 'no proof support'}`);
    details.append(tensors); body.append(details); record.append(body); $('models-view').append(record);
  }
}
function coverageView(result) {
  const {manifest:m, entry:t} = result;
  const wrapper = node('section', undefined, 'coverage');
  const header = node('div', undefined, 'coverage-header');
  const nav = node('div', undefined, 'coverage-nav');
  nav.setAttribute('role','group'); nav.setAttribute('aria-label','Inspect proof coverage');
  header.append(node('h3', 'Where this calculation sits'), nav);
  const body = node('div', undefined, 'coverage-body');
  const visual = node('div');
  const plot = node('div', undefined, 'coverage-plot'); plot.setAttribute('aria-hidden','true');
  const legend = node('p', undefined, 'coverage-legend'); visual.append(plot,legend);
  const caption = node('div', undefined, 'coverage-caption'); caption.setAttribute('aria-live','polite');
  body.append(visual,caption); wrapper.append(header,body);
  const controls = [];
  function view(kind) {
    for(const [id,button] of controls) button.setAttribute('aria-pressed',String(id === kind));
    plot.replaceChildren(); caption.replaceChildren(); plot.dataset.view=kind;
    if(kind === 'model') {
      for(const tensor of m.tensors) plot.append(node('span', undefined, tensor.name === t.name ? 'selected' : ''));
      legend.textContent=`Each square is one tensor, ${m.tensors.length} in total`;
      caption.append(node('h3',m.model.name),node('p','The highlighted tensor contains this proof’s calculation. The other tensors are not checked by this file.'),node('p',t.name,'fingerprint'));
    } else if(kind === 'operation') {
      // These are conceptual stages, not a measured execution graph or progress percentage.
      for(let i=0;i<5;i++) plot.append(node('span',undefined,i===1?'selected':''));
      legend.textContent='Stages of the operation, not an execution trace';
      caption.append(node('h3','Only the integer arithmetic'),node('p','Input quantization → integer row group → scaling → accumulation → output.'),node('p','This proof checks one integer group. Quantization, scales, accumulation and rounding remain outside its claim.'),node('p',t.name,'fingerprint'));
    } else {
      const rows=t.groth16.rows_per_group, first=result.group*rows;
      for(let i=0;i<rows;i++) plot.append(node('span',undefined,'selected'));
      legend.textContent=`Each block is one of the ${rows} rows in this group`;
      caption.append(node('h3',`Rows ${first}–${first+rows-1}`),node('p',`Group ${result.group} of ${t.groth16.groups.length} registered groups for this tensor. Q4_K × Q8_K integer arithmetic.`),node('p','Private weights are bound to the registered commitment. Activation values and sums are public.'));
    }
  }
  for(const [id,label] of [['model','Model'],['operation','Operation'],['rows','Rows']]) {
    const button=node('button',label); button.type='button'; button.addEventListener('click',()=>view(id));controls.push([id,button]);nav.append(button);
  }
  view('rows'); return wrapper;
}
function resultView(result, ms, label) {
  const out = $('result-view'); out.hidden=false; out.dataset.state = result.status;
  const titles = {verified:'Proof accepted.', invalid:'Proof rejected.', unsupported:'Unsupported proof format.',
    'unknown-model':'Registration not found.', unavailable:'Verification unavailable.'};
  const heading=node('div',undefined,'result-heading'), title=node('div');
  title.append(node('div', label || 'Your proof file', 'eyebrow'), node('h2', titles[result.status] || 'Verification could not complete.'));
  heading.append(title,node('div',result.accept?'✓':'×',result.accept?'verdict-seal ok':'verdict-seal bad'));
  out.replaceChildren(heading);
  let explanation = result.error;
  if (result.status === 'invalid' && result.entry) {
    if (/q8.*range/.test(result.error)) explanation = 'A public activation value is outside the allowed range for this computation.';
    else if (/s[12].*range/.test(result.error)) explanation = 'A public arithmetic sum is outside the allowed range for this computation.';
    else if (/commitment differs/.test(result.error)) explanation = 'The proof does not match the registered weights for this operation segment.';
    else if (/public signal/.test(result.error)) explanation = 'The proof contains malformed or missing public numbers.';
    else if (/proof verification failed/.test(result.error)) explanation = 'The proof does not verify against its supplied public inputs.';
  }
  out.append(node('p', result.accept ? 'The integer arithmetic checks out, and the weights match the registered commitment.' : explanation, 'result-lead'));
  out.append(node('p', 'The prompt, the answer and the complete inference are not verified by this proof.', 'notice'));
  if (result.manifest && result.entry) {
    const {manifest:m, entry:t} = result, facts = node('dl', undefined, 'facts');
    for (const [name, value] of [
      ['Model', m.model.name + ', ' + fileTypeLabel(m)],
      ['Checked', result.accept ? `One row group of ${t.groth16.rows_per_group} rows` : 'Not accepted'],
      ['Weight commitment', result.bound ? 'Matches the registered model' : 'Not confirmed'],
      ['Verification time', `${ms} ms in this browser`]
    ]) { const pair = node('div'); pair.append(node('dt', name), node('dd', value)); facts.append(pair); }
    out.append(facts);
    if(result.accept) out.append(coverageView(result));
    const details = node('details'), table = node('table'); details.append(node('summary', 'Technical details and trust assumptions'));
    tableRow(table, 'Registration ID', m.manifest_id); tableRow(table, 'Tensor', t.name);
    tableRow(table, 'Circuit', t.groth16.circuit);
    tableRow(table, 'Rows', `${result.group * t.groth16.rows_per_group} through ${(result.group + 1) * t.groth16.rows_per_group - 1} (group ${result.group})`);
    tableRow(table, 'Pairing check', result.pairing ? 'Passed' : 'Not confirmed');
    tableRow(table, 'Weight commitment', result.bound ? 'Matches' : 'Not confirmed');
    tableRow(table, 'Privacy', 'Weights are private. Activation numbers and arithmetic sums are public.');
    tableRow(table, 'Trust', 'Registered by this project. Independent review is pending. The proving parameters come from an experimental single-contributor setup.');
    if (result.error) tableRow(table, 'Reason', result.error);
    details.append(table); out.append(details);
  }
  out.focus({preventScroll:true});
  const reduced = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
  out.scrollIntoView({behavior:reduced?'instant':'smooth', block:'start'});
}
async function verifyPackage(value, label) {
  if (verifying) return;
  verifying = true; document.dispatchEvent?.(new CustomEvent('receipts-verification', {detail:{active:true}})); $('run').disabled = true; $('package-file').disabled = true;
  $('status').textContent = 'Checking the proof against the registered model in your browser…';
  $('result-view').hidden = false;
  $('result-view').dataset.state = 'checking';
  $('result-view').replaceChildren(node('h2', 'Checking proof…'));
  const start = performance.now();
  try {
    const result = await ProofPackage.verify(value, DATA, ReceiptsVerifier, globalThis.snarkjs);
    resultView(result, Math.round(performance.now() - start), label);
    return result;
  } catch (e) {
    resultView({status:'unavailable', accept:false, error:'Verification could not finish. Retry or use the offline verifier.'}, 0, label);
  } finally { verifying = false; document.dispatchEvent?.(new CustomEvent('receipts-verification', {detail:{active:false}})); $('run').disabled = false; $('package-file').disabled = false; $('status').textContent = ''; }
}
async function verifySelected() {
  if (verifying) return;
  const file = selectedFile || $('package-file').files[0];
  if (!file) { $('status').textContent = 'Choose one proof file first, or try an example.'; return; }
  if (file.size > ProofPackage.MAX_BYTES) {
    resultView({status:'invalid', error:'This checkpoint accepts proof files up to 2 MiB.'}, 0); return;
  }
  let value;
  verifying = true; document.dispatchEvent?.(new CustomEvent('receipts-verification', {detail:{active:true}})); $('run').disabled = true; $('package-file').disabled = true;
  try { value = JSON.parse(await file.text()); }
  catch { resultView({status:'invalid', error:'This file could not be read as a JSON proof package. Export it again from the prover.'}, 0); return; }
  finally { verifying = false; $('run').disabled = false; $('package-file').disabled = false; }
  await verifyPackage(value, file.name);
}
function renderExamples() {
  $('examples').replaceChildren();
  for (const [i, e] of (DATA.examples || []).entries()) {
    const button = node('button', i ? 'Try an invalid proof' : 'Try a valid proof', 'secondary');
    button.addEventListener('click', () => verifyPackage(ProofPackage.envelope(e), e.label));
    $('examples').append(button);
  }
  $('download-example').disabled = !DATA.examples?.length;
}
function selectFile(file) {
  if (verifying) return;
  selectedFile = file;
  $('file-label').textContent = file ? file.name : 'Choose a proof file.';
  $('status').textContent = '';
  $('result-view').hidden = false;
  $('result-view').dataset.state = 'pending';
  $('result-view').replaceChildren(node('h2', 'File selected. Not checked yet.'));
}
async function api(path, options = {}) {
  const response = await fetch('/api/local' + path, {...options, headers:{'X-Prover-Token':LOCAL.token, ...options.headers}});
  let body;
  try { body = await response.json(); } catch { throw Error('The local prover returned an unreadable response. Restart the workspace.'); }
  if (!response.ok) throw Error(typeof body.detail === 'string' ? body.detail : 'The local prover could not accept this request.');
  return body;
}
const stages = [['model','Checking model'], ['inference','Running inference'], ['witness','Preparing proof inputs'],
  ['proving','Generating proof'], ['checking','Checking proof'], ['export','Preparing download']];
function renderJob(job) {
  const current = stages.findIndex(([id]) => id === job.stage);
  $('job-view').hidden = false;
  $('progress').replaceChildren(...stages.map(([id, label], i) => {
    const item = node('li', label); item.dataset.state = job.status === 'complete' || i < current ? 'done' : i === current && job.status === 'running' ? 'active' : 'pending'; return item;
  }));
  $('job-status').textContent = job.status === 'complete' ? `Done in ${job.elapsed_seconds} s. Your proof is ready to download.` :
    job.status === 'failed' ? 'Stopped: ' + job.error : job.status === 'cancelled' ? 'Cancelled. You can start another run.' : `Working ${HOSTED ? 'on the server' : 'locally'}, ${job.elapsed_seconds} s so far`;
  const done = ['complete','failed','cancelled'].includes(job.status);
  $('prompt').disabled = !done; $('local-model').disabled = !done;
  $('cancel-button').hidden = done;
  $('generate-button').disabled = !done;
  $('generate-button').textContent = done && job.status !== 'complete' ? 'Try again' : 'Run and generate proof';
  $('generation-output').hidden = job.status !== 'complete';
  $('download-proof').disabled = !generatedPackage; $('check-generated').disabled = !generatedPackage;
  if (job.status === 'complete') {
    $('answer').textContent = job.answer;
    const table = node('table');
    for (const [label, value] of Object.entries(job.measurements || {})) tableRow(table, label.replaceAll('_',' '), value);
    $('run-measurements').replaceChildren(table); $('run-details').hidden = false;
  }
}
async function pollJob() {
  if (!jobId || polling) return;
  polling = true;
  const requestedId = jobId;
  try {
    const job = await api('/jobs/' + requestedId);
    if (requestedId !== jobId) return;
    renderJob(job);
    if (job.status === 'complete') {
      const value = await api('/jobs/' + requestedId + '/proof');
      if (requestedId !== jobId) return;
      generatedPackage = value;
      $('download-proof').disabled = false; $('check-generated').disabled = false;
    }
    else if (job.status === 'running') setTimeout(pollJob, 1000);
  } catch (e) {
    if (requestedId !== jobId) return;
    $('job-status').textContent = 'Connection interrupted: ' + e.message + ' Retrying in 3 seconds.';
    setTimeout(pollJob, 3000);
  } finally {
    polling = false;
    if (requestedId !== jobId && jobId) setTimeout(pollJob, 0);
  }
}
async function loadLocal() {
  if (!LOCAL) return;
  if (HOSTED) {
    $('show-generate').textContent = 'Generate on server';
    $('generate').setAttribute('aria-label', 'Generate on server');
    $('run-details').querySelector('p.small').textContent = 'Measured on the hosted server; not certified by the proof.';
  }
  workspaceMode('generate');
  $('local-unavailable').hidden = true; $('generate-form').hidden = false; $('generate-button').disabled = true;
  try {
    const config = await api('/config');
    $('local-model').replaceChildren(...config.models.map(m => new Option(m.name, m.id)));
    function readiness() {
      const m = config.models.find(m => m.id === $('local-model').value);
      $('readiness').textContent = m?.ready ? (HOSTED ? 'Ready. Prompts run on this server. This login shares one workspace and its latest result.' : 'Model and proving tools found. Everything runs on this computer.') : (m?.issues || ['No supported local model.']).join(' ');
      $('generate-button').disabled = !m?.ready;
    }
    $('local-model').addEventListener('change', readiness); readiness();
    if (config.job) {
      jobId = config.job.id; $('prompt').value = config.job.prompt;
      renderJob(config.job); await pollJob();
    }
  } catch (e) { $('readiness').textContent = e.message; }
}
function init() {
  $('show-verify').addEventListener('click', () => workspaceMode('verify'));
  $('show-generate').addEventListener('click', () => workspaceMode('generate'));
  $('model-search').addEventListener('input', renderModels);
  $('run').addEventListener('click', verifySelected);
  $('package-file').addEventListener('change', e => selectFile(e.target.files[0]));
  $('drop-zone').addEventListener('dragover', e => { e.preventDefault(); $('drop-zone').classList.add('drag'); });
  $('drop-zone').addEventListener('dragleave', () => $('drop-zone').classList.remove('drag'));
  $('drop-zone').addEventListener('drop', e => {
    e.preventDefault(); $('drop-zone').classList.remove('drag');
    if (e.dataTransfer.files.length !== 1) { $('status').textContent = 'Choose one proof package at a time.'; return; }
    selectFile(e.dataTransfer.files[0]);
  });
  $('download-example').addEventListener('click', () => { if (DATA.examples?.length) download(ProofPackage.envelope(DATA.examples[0]), 'example.llamaproof'); });
  $('generate-form').addEventListener('submit', async e => {
    e.preventDefault(); if (jobId && !$('cancel-button').hidden) return;
    $('generate-button').disabled = true; $('generation-output').hidden = true; $('run-details').hidden = true; generatedPackage = null;
    try {
      const job = await api('/jobs', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({model:$('local-model').value, prompt:$('prompt').value})});
      jobId = job.id; renderJob(job); await pollJob();
    } catch (error) { $('readiness').textContent = error.message; $('generate-button').disabled = false; }
  });
  $('cancel-button').addEventListener('click', async () => {
    try { await api('/jobs/' + jobId + '/cancel', {method:'POST'}); await pollJob(); }
    catch (error) { $('job-status').textContent = error.message; }
  });
  $('download-proof').addEventListener('click', () => { if (generatedPackage) download(generatedPackage, 'computation-proof.llamaproof'); });
  $('check-generated').addEventListener('click', () => { if (generatedPackage) verifyPackage(generatedPackage, 'Your generated proof'); });
  renderModels(); renderExamples(); loadLocal();
}
init();
