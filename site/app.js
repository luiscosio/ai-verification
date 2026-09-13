const $ = id => document.getElementById(id);
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
function renderModels() {
  $('models-view').replaceChildren();
  const query = $('model-search').value.trim().toLowerCase();
  const models = DATA.manifests.filter(m => (m.model.name + ' ' + m.model.file_sha256).toLowerCase().includes(query));
  const supported = DATA.manifests.filter(m => m.tensors.some(t => t.groth16)).length;
  $('catalog-summary').textContent = `${DATA.manifests.length} model files recorded · ${supported} with experimental proof coverage`;
  if (!models.length) $('models-view').append(node('p', 'No registered models match your search.', 'small'));
  for (const m of models) {
    const card = node('div', undefined, 'card'), table = node('table');
    const committed = m.tensors.filter(t => t.groth16), groups = committed.reduce((n, t) => n + t.groth16.groups.length, 0);
    card.append(node('h3', m.model.name));
    card.append(node('p', committed.length ? 'Experimental proofs available' : 'Fingerprint only · proofs unavailable', committed.length ? 'ok' : 'small'));
    card.append(node('p', committed.length ? `${committed.length} of ${m.tensors.length} tensors have registered integer row groups (${groups} groups). No full-inference coverage.` : 'This exact file is recorded. Proof verification has not been registered for it yet.', 'small'));
    card.append(node('p', m.model.file_sha256, 'fingerprint'));
    const registrationDetails = node('details'); registrationDetails.append(node('summary', 'Registration and trust details'));
    tableRow(table, 'Registration', m.manifest_id);
    tableRow(table, 'Model file SHA-256', m.model.file_sha256);
    tableRow(table, 'Execution metadata', `${m.execution.statement}; ${m.execution.backend}; ${m.execution.threads} threads. This checkpoint does not prove full execution.`);
    tableRow(table, 'Trust', 'Project registry; independent registrar review pending. Experimental single-contributor setup.');
    tableRow(table, 'Coverage', committed.length ? 'Q4_K integer row groups; no complete operation or next-token proof.' : 'File and tensor identity only; no Groth16 acceptance available.');
    registrationDetails.append(table);
    const button = node('button', 'Download registration', 'secondary');
    button.addEventListener('click', () => download(m, 'registration.json')); registrationDetails.append(button);
    const details = node('details'), tensors = node('table'); details.append(node('summary', `${m.tensors.length} tensors`));
    for (const t of m.tensors) tableRow(tensors, t.name, `${t.type}; ${t.shape.join(' × ')}; ${t.groth16 ? t.groth16.groups.length + ' registered row groups' : 'not covered'}`);
    details.append(tensors); registrationDetails.append(details); card.append(registrationDetails); $('models-view').append(card);
  }
}
function resultView(result, ms, label) {
  const out = $('result-view'); out.dataset.state = result.status;
  const titles = {verified:'Computation proof verified', invalid:'Proof not accepted', unsupported:'Unsupported proof format',
    'unknown-model':'Unknown model registration', unavailable:'Verification unavailable'};
  out.replaceChildren(node('div', label || 'Verification result', 'eyebrow'), node('h2', titles[result.status] || 'Verification could not complete', result.accept ? 'ok' : ''));
  let explanation = result.error;
  if (result.status === 'invalid' && result.entry) {
    if (/q8.*range/.test(result.error)) explanation = 'A public activation value is outside the allowed range for this computation.';
    else if (/s[12].*range/.test(result.error)) explanation = 'A public arithmetic sum is outside the allowed range for this computation.';
    else if (/commitment differs/.test(result.error)) explanation = 'The proof does not match the registered weights for this operation segment.';
    else if (/public signal/.test(result.error)) explanation = 'The proof contains malformed or missing public numbers.';
    else if (/proof verification failed/.test(result.error)) explanation = 'The proof does not verify against its supplied public inputs.';
  }
  out.append(node('p', result.accept ? 'The arithmetic and registered weight commitment passed the checks for this operation segment.' : explanation));
  out.append(node('p', 'The prompt, generated answer and complete inference are not verified by this proof.', 'notice'));
  if (result.manifest && result.entry) {
    const {manifest:m, entry:t} = result, facts = node('dl', undefined, 'facts');
    for (const [name, value] of [
      ['Model registration', m.model.name + ' · project registry; independent review pending'],
      ['Coverage', `One group of ${t.groth16.rows_per_group} rows: Q4_K × Q8_K integer arithmetic. Scales and other operations are outside this proof.`],
      ['Privacy', 'Weights are private. Activation numbers and arithmetic sums are public.'],
      ['Verification', `In this browser · ${ms} ms · experimental single-contributor setup`]
    ]) { const pair = node('div'); pair.append(node('dt', name), node('dd', value)); facts.append(pair); }
    out.append(facts);
    const details = node('details'), table = node('table'); details.append(node('summary', 'Technical checks'));
    tableRow(table, 'Registration ID', m.manifest_id); tableRow(table, 'Tensor', t.name);
    tableRow(table, 'Circuit', t.groth16.circuit);
    tableRow(table, 'Rows', `${result.group * t.groth16.rows_per_group} through ${(result.group + 1) * t.groth16.rows_per_group - 1} (group ${result.group})`);
    tableRow(table, 'Pairing', result.pairing ? 'Passes' : 'Not accepted / not completed');
    tableRow(table, 'Weight commitment', result.bound ? 'Matches' : 'Not accepted / not completed');
    if (result.error) tableRow(table, 'Reason', result.error);
    details.append(table); out.append(details);
  }
  out.focus({preventScroll:true});
  out.scrollIntoView({behavior:'smooth', block:'start'});
}
async function verifyPackage(value, label) {
  if (verifying) return;
  verifying = true; $('run').disabled = true; $('package-file').disabled = true;
  $('status').textContent = 'Checking the proof and trusted registration in your browser…';
  $('result-view').dataset.state = 'checking';
  $('result-view').replaceChildren(node('h2', 'Checking proof…'));
  const start = performance.now();
  try {
    const result = await ProofPackage.verify(value, DATA, ReceiptsVerifier, globalThis.snarkjs);
    resultView(result, Math.round(performance.now() - start), label);
    return result;
  } catch (e) {
    resultView({status:'unavailable', accept:false, error:'Verification could not finish. Retry or use the offline verifier.'}, 0, label);
  } finally { verifying = false; $('run').disabled = false; $('package-file').disabled = false; $('status').textContent = ''; }
}
async function verifySelected() {
  if (verifying) return;
  const file = selectedFile || $('package-file').files[0];
  if (!file) { $('status').textContent = 'Choose one proof file first, or try an example.'; return; }
  if (file.size > ProofPackage.MAX_BYTES) {
    resultView({status:'invalid', error:'This checkpoint accepts proof files up to 2 MiB.'}, 0); return;
  }
  let value;
  verifying = true; $('run').disabled = true; $('package-file').disabled = true;
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
  $('result-view').dataset.state = 'pending';
  $('result-view').replaceChildren(node('h2', 'File selected · not checked yet'));
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
  $('job-status').textContent = job.status === 'complete' ? `Ready · ${job.elapsed_seconds}s total. Your proof is ready to download.` :
    job.status === 'failed' ? 'Stopped: ' + job.error : job.status === 'cancelled' ? 'Cancelled. You can start another run.' : `Working locally · ${job.elapsed_seconds}s elapsed`;
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
  $('local-unavailable').hidden = true; $('generate-form').hidden = false; $('generate-button').disabled = true;
  try {
    const config = await api('/config');
    $('local-model').replaceChildren(...config.models.map(m => new Option(m.name, m.id)));
    function readiness() {
      const m = config.models.find(m => m.id === $('local-model').value);
      $('readiness').textContent = m?.ready ? 'Model and proving tools found. Everything runs on this computer.' : (m?.issues || ['No supported local model.']).join(' ');
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
  $('check-generated').addEventListener('click', () => { if (generatedPackage) verifyPackage(generatedPackage, 'Your local computation proof'); });
  renderModels(); renderExamples(); loadLocal();
}
init();
