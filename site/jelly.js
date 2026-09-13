// Decorative only: this scene never receives proof data or determines a verdict.
// Pinned independently from the verifier. Failure leaves the static illustration intact.
const stage = document.getElementById("jelly-stage");
const motionButton = document.getElementById("motion-toggle");
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
let proofBusy = false;
let paused = reducedMotion.matches,
  visible = true,
  active = false,
  frame = 0;
let renderer,
  scene,
  camera,
  sculpture,
  material,
  sliceMaterial,
  environment,
  geometry,
  sliceGeometry;
let resizeObserver, intersectionObserver;
let time = 0,
  previous = 0,
  pointerX = 0,
  pointerY = 0;

try {
  const THREE = ReceiptsThree;
  renderer = new THREE.WebGLRenderer({
    alpha: true,
    antialias: true,
    powerPreference: "low-power",
  });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
  renderer.setClearColor(0x000000, 0);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.3;
  stage.append(renderer.domElement);
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(32, 1, 0.1, 40);
  camera.position.set(0, 0.3, 7.4);
  camera.lookAt(0, -0.04, 0);

  // Softbox reflections provide gloss without external image assets.
  const studio = new THREE.Scene();
  studio.background = new THREE.Color(0xc9bfd9);
  const panelGeometry = new THREE.PlaneGeometry(1, 1);
  const panelMaterials = [];
  function panel(color, intensity, x, y, z, width, height) {
    const mat = new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide });
    mat.color.multiplyScalar(intensity);
    panelMaterials.push(mat);
    const mesh = new THREE.Mesh(panelGeometry, mat);
    mesh.position.set(x, y, z);
    mesh.scale.set(width, height, 1);
    mesh.lookAt(0, 0, 0);
    studio.add(mesh);
  }
  panel(0xfff2dc, 5, -3, 4, 3, 3, 5);
  panel(0xffffff, 4, 4, 1, 2, 1.5, 5);
  panel(0xe2d0ff, 3, 0, 2, -4, 5, 3);
  const pmrem = new THREE.PMREMGenerator(renderer);
  environment = pmrem.fromScene(studio, 0.025);
  scene.environment = environment.texture;
  pmrem.dispose();
  panelGeometry.dispose();
  panelMaterials.forEach((m) => m.dispose());
  scene.add(new THREE.HemisphereLight(0xfff4e9, 0x756384, 2.1));
  const key = new THREE.DirectionalLight(0xffe9cd, 3.5);
  key.position.set(-3, 4, 4);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0xb8a2ff, 2.8);
  rim.position.set(4, 1, -2);
  scene.add(rim);

  sculpture = new THREE.Group();
  sculpture.rotation.set(0.15, 0, -0.2);
  scene.add(sculpture);
  // A rounded, fluted jelly mould. The grooves and elastic deformation are real geometry.
  geometry = new THREE.SphereGeometry(1, 112, 72);
  const positions = geometry.attributes.position;
  for (let i = 0; i < positions.count; i++) {
    const x = positions.getX(i),
      y = positions.getY(i),
      z = positions.getZ(i);
    const angle = Math.atan2(z, x),
      r = Math.hypot(x, z);
    const flute = 1 + 0.065 * Math.cos(angle * 12) * Math.pow(r, 0.6);
    const radius = Math.pow(r, 0.55) * flute * (1 - 0.12 * y);
    positions.setXYZ(
      i,
      Math.cos(angle) * radius * 1.27,
      Math.sign(y) * Math.pow(Math.abs(y), 0.65) * 1.23,
      Math.sin(angle) * radius * 1.27,
    );
  }
  geometry.computeVertexNormals();
  const base = new Float32Array(positions.array);
  material = new THREE.MeshPhysicalMaterial({
    color: 0xee9a63,
    metalness: 0,
    roughness: 0.19,
    transmission: 0.55,
    thickness: 2.4,
    ior: 1.36,
    clearcoat: 1,
    clearcoatRoughness: 0.12,
    attenuationColor: 0xe58977,
    attenuationDistance: 3.2,
    envMapIntensity: 1.2,
    side: THREE.DoubleSide,
  });
  const jelly = new THREE.Mesh(geometry, material);
  sculpture.add(jelly);

  // A lavender ribbon around the volume, offset slightly like a lifted sliver.
  sliceGeometry = new THREE.SphereGeometry(
    1,
    112,
    4,
    0,
    Math.PI * 2,
    Math.PI / 2 - 0.045,
    0.09,
  );
  sliceMaterial = new THREE.MeshPhysicalMaterial({
    color: 0x8361bf,
    metalness: 0.12,
    roughness: 0.18,
    clearcoat: 1,
    transmission: 0.2,
    thickness: 0.25,
    envMapIntensity: 1.5,
  });
  const slice = new THREE.Mesh(sliceGeometry, sliceMaterial);
  sculpture.add(slice);
  const slicePositions = sliceGeometry.attributes.position;
  for (let i = 0; i < slicePositions.count; i++) {
    const x = slicePositions.getX(i),
      y = slicePositions.getY(i),
      z = slicePositions.getZ(i);
    const a = Math.atan2(z, x),
      r = Math.hypot(x, z),
      f = 1 + 0.065 * Math.cos(a * 12) * Math.pow(r, 0.6);
    const radius = Math.pow(r, 0.55) * f * (1 - 0.12 * y) * 1.012;
    slicePositions.setXYZ(
      i,
      Math.cos(a) * radius * 1.27,
      Math.sign(y) * Math.pow(Math.abs(y), 0.65) * 1.23,
      Math.sin(a) * radius * 1.27,
    );
  }
  sliceGeometry.computeVertexNormals();
  const sliceBase = new Float32Array(slicePositions.array);

  // A small floor shadow anchors the sculpture; all pixels are generated locally.
  const shadowCanvas = document.createElement("canvas");
  shadowCanvas.width = 128;
  shadowCanvas.height = 128;
  const ctx = shadowCanvas.getContext("2d");
  const gradient = ctx.createRadialGradient(64, 64, 2, 64, 64, 64);
  gradient.addColorStop(0, "rgba(70,43,87,.22)");
  gradient.addColorStop(1, "rgba(70,43,87,0)");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, 128, 128);
  const shadowTexture = new THREE.CanvasTexture(shadowCanvas);
  const shadowGeometry = new THREE.PlaneGeometry(3.9, 1.1);
  const shadowMaterial = new THREE.MeshBasicMaterial({
    map: shadowTexture,
    transparent: true,
    depthWrite: false,
  });
  const shadow = new THREE.Mesh(shadowGeometry, shadowMaterial);
  shadow.position.set(0, -1.59, -0.25);
  shadow.rotation.x = -0.85;
  scene.add(shadow);

  function draw() {
    const breathing = Math.sin(time * 0.9) * 0.022;
    for (let i = 0; i < positions.count; i++) {
      const j = i * 3,
        x = base[j],
        y = base[j + 1],
        z = base[j + 2];
      const wobble = Math.sin(y * 2.8 + time * 1.25) * 0.027;
      positions.setXYZ(
        i,
        x * (1 + breathing) + wobble,
        y * (1 - breathing * 0.8),
        z * (1 + breathing) + Math.sin(time * 0.85 + y * 2) * 0.018,
      );
    }
    positions.needsUpdate = true;
    geometry.computeVertexNormals();
    for (let i = 0; i < slicePositions.count; i++) {
      const j = i * 3,
        x = sliceBase[j],
        y = sliceBase[j + 1],
        z = sliceBase[j + 2];
      slicePositions.setXYZ(
        i,
        x * (1 + breathing) + Math.sin(y * 2.8 + time * 1.25) * 0.027,
        y * (1 - breathing * 0.8),
        z * (1 + breathing) + Math.sin(time * 0.85 + y * 2) * 0.018,
      );
    }
    slicePositions.needsUpdate = true;
    sliceGeometry.computeVertexNormals();
    sculpture.rotation.y = time * 0.095 + pointerX * 0.12;
    sculpture.rotation.x =
      0.15 + Math.sin(time * 0.6) * 0.035 + pointerY * 0.06;
    sculpture.position.y = Math.sin(time * 0.8) * 0.035;
    renderer.render(scene, camera);
  }
  function tick(now) {
    frame = 0;
    if (!active || paused || proofBusy || !visible || document.hidden) {
      previous = 0;
      return;
    }
    // Cap to 30 fps and avoid jumps after resuming an inactive tab.
    if (previous && now - previous < 32) {
      frame = requestAnimationFrame(tick);
      return;
    }
    if (previous) time += Math.min((now - previous) / 1000, 0.05);
    previous = now;
    draw();
    frame = requestAnimationFrame(tick);
  }
  function schedule() {
    if (frame) cancelAnimationFrame(frame);
    frame = 0;
    previous = 0;
    if (active && !paused && !proofBusy && visible && !document.hidden)
      frame = requestAnimationFrame(tick);
  }
  function resize() {
    const w = stage.clientWidth,
      h = stage.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.position.z = camera.aspect < 1 ? 8.6 : 7.4;
    camera.updateProjectionMatrix();
    draw();
  }
  function buttonState() {
    motionButton.textContent = paused ? "Play motion" : "Pause motion";
    motionButton.setAttribute("aria-pressed", String(paused));
  }
  motionButton.addEventListener("click", () => {
    paused = !paused;
    buttonState();
    schedule();
  });
  reducedMotion.addEventListener("change", (event) => {
    paused = event.matches;
    buttonState();
    schedule();
  });
  document.addEventListener("receipts-verification", (event) => {
    proofBusy = event.detail?.active === true;
    schedule();
  });
  document.addEventListener("visibilitychange", schedule);
  stage.parentElement.addEventListener("pointermove", (event) => {
    if (paused) return;
    const r = stage.getBoundingClientRect();
    pointerX = (event.clientX - r.left) / r.width - 0.5;
    pointerY = (event.clientY - r.top) / r.height - 0.5;
  });
  stage.parentElement.addEventListener("pointerleave", () => {
    pointerX = 0;
    pointerY = 0;
  });
  renderer.domElement.addEventListener("webglcontextlost", (event) => {
    event.preventDefault();
    active = false;
    schedule();
    stage.dataset.ready = "false";
    motionButton.hidden = true;
  });
  // No GPU activity while off-screen, in a background tab, or paused.
  intersectionObserver = new IntersectionObserver((entries) => {
    visible = entries[0].isIntersecting;
    schedule();
  });
  intersectionObserver.observe(stage);
  resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(stage);
  active = true;
  resize();
  stage.dataset.ready = "true";
  motionButton.hidden = false;
  buttonState();
  schedule();
  window.addEventListener("pageshow", () => {
    active = true;
    schedule();
  });
  window.addEventListener("pagehide", (event) => {
    active = false;
    schedule();
    if (event.persisted) return;
    resizeObserver.disconnect();
    intersectionObserver.disconnect();
    geometry.dispose();
    sliceGeometry.dispose();
    material.dispose();
    sliceMaterial.dispose();
    environment.dispose();
    shadowTexture.dispose();
    shadowGeometry.dispose();
    shadowMaterial.dispose();
    renderer.dispose();
  });
} catch (error) {
  active = false;
  if (frame) cancelAnimationFrame(frame);
  resizeObserver?.disconnect();
  intersectionObserver?.disconnect();
  renderer?.dispose();
  renderer?.domElement.remove();
  stage.dataset.ready = "false";
  motionButton.hidden = true;
}
