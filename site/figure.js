// Decorative only: this scene never receives proof data or determines a verdict.
// Pinned independently from the verifier. Failure leaves the static illustration intact.
//
// What it shows. A weight matrix as a slab of frosted glass tiles: the verifier never
// reads them. One band of rows lifts out of the slab, an input pulse travels along it,
// its outputs accumulate at the edge, and a seal closes around the band. Only that band
// is ever lit, because the proof covers one integer row group and nothing else.
const stage = document.getElementById("figure-stage");
const motionButton = document.getElementById("motion-toggle");
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
let proofBusy = false;
let paused = reducedMotion.matches,
  visible = true,
  active = false,
  frame = 0;
let renderer, scene, camera, environment;
let resizeObserver, intersectionObserver;
const disposables = [];
const CYCLE = 12; // seconds per lift, sweep, seal and release
let time = CYCLE * 0.7, // the still frame shows a sealed band
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
  renderer.toneMappingExposure = 1.1;
  stage.append(renderer.domElement);
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(30, 1, 0.1, 40);

  // Softbox reflections provide gloss without external image assets.
  const studio = new THREE.Scene();
  studio.background = new THREE.Color(0xcfc6dc);
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
  scene.add(new THREE.HemisphereLight(0xfff4e9, 0x5e4a70, 1.6));
  const key = new THREE.DirectionalLight(0xffe2bd, 4.6);
  key.position.set(-4, 3.2, 2.5);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0xb8a2ff, 2.4);
  rim.position.set(4, 2, -3);
  scene.add(rim);

  const rig = new THREE.Group();
  scene.add(rig);

  // The matrix: COLS x ROWS frosted tiles in one instanced draw call.
  const COLS = 56,
    ROWS = 36,
    PITCH = 0.062,
    SIZE = 0.052,
    BASE = 0.09,
    BAND = 5;
  const WIDTH = COLS * PITCH,
    DEPTH = ROWS * PITCH;
  const tileGeometry = new THREE.BoxGeometry(SIZE, 1, SIZE);
  tileGeometry.translate(0, 0.5, 0); // tiles grow upward from the slab
  const tileMaterial = new THREE.MeshPhysicalMaterial({
    color: 0xffffff,
    metalness: 0,
    roughness: 0.42,
    transmission: 0.18,
    thickness: 0.6,
    ior: 1.4,
    clearcoat: 0.7,
    clearcoatRoughness: 0.25,
    attenuationColor: 0xf0a070,
    attenuationDistance: 1.4,
    envMapIntensity: 0.75,
  });
  const tiles = new THREE.InstancedMesh(tileGeometry, tileMaterial, COLS * ROWS);
  tiles.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  rig.add(tiles);
  disposables.push(tileGeometry, tileMaterial);
  const dummy = new THREE.Object3D();
  const color = new THREE.Color();
  const frosted = new THREE.Color(0xe89a66);
  const lit = new THREE.Color(0x8f6ad8);
  const hot = new THREE.Color(0xfff3ff);
  const jitter = new Float32Array(COLS * ROWS);
  for (let i = 0; i < jitter.length; i++) {
    const s = Math.sin(i * 12.9898) * 43758.5453;
    jitter[i] = s - Math.floor(s);
  }
  for (let i = 0; i < COLS * ROWS; i++) tiles.setColorAt(i, frosted);
  tiles.instanceColor.setUsage(THREE.DynamicDrawUsage);

  // A plate under the tiles keeps the slab reading as one object.
  const plateGeometry = new THREE.BoxGeometry(WIDTH + 0.1, 0.03, DEPTH + 0.1);
  const plateMaterial = new THREE.MeshPhysicalMaterial({
    color: 0xd8bcab,
    roughness: 0.75,
    clearcoat: 0.3,
    envMapIntensity: 0.5,
  });
  const plate = new THREE.Mesh(plateGeometry, plateMaterial);
  plate.position.y = -0.02;
  rig.add(plate);
  disposables.push(plateGeometry, plateMaterial);

  // The input: a pulse of light that travels along the lifted rows.
  const pulseGeometry = new THREE.BoxGeometry(0.05, 0.018, BAND * PITCH + 0.05);
  const pulseMaterial = new THREE.MeshBasicMaterial({
    color: 0xfff4de,
    transparent: true,
    opacity: 0,
    depthWrite: false,
  });
  const pulse = new THREE.Mesh(pulseGeometry, pulseMaterial);
  rig.add(pulse);
  disposables.push(pulseGeometry, pulseMaterial);
  const glow = new THREE.PointLight(0xc3a9ff, 0, 1.8, 2);
  rig.add(glow);

  // The outputs: one point per lifted row, filling in as the pulse crosses.
  const dotGeometry = new THREE.SphereGeometry(0.04, 16, 12);
  const dotMaterial = new THREE.MeshBasicMaterial({
    color: 0xfff7e6,
    transparent: true,
    opacity: 0,
    depthWrite: false,
  });
  const dots = new THREE.InstancedMesh(dotGeometry, dotMaterial, BAND);
  dots.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  rig.add(dots);
  disposables.push(dotGeometry, dotMaterial);

  // The seal: a thin frame that closes around the band once its outputs are in.
  const railGeometry = new THREE.BoxGeometry(1, 0.016, 0.016);
  const railMaterial = new THREE.MeshBasicMaterial({
    color: 0x8f72d6,
    transparent: true,
    opacity: 0,
    depthWrite: false,
  });
  const rails = new THREE.InstancedMesh(railGeometry, railMaterial, 4);
  rails.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  rig.add(rails);
  disposables.push(railGeometry, railMaterial);

  // A soft floor shadow anchors the slab; all pixels are generated locally.
  const shadowCanvas = document.createElement("canvas");
  shadowCanvas.width = 128;
  shadowCanvas.height = 128;
  const ctx = shadowCanvas.getContext("2d");
  const gradient = ctx.createRadialGradient(64, 64, 4, 64, 64, 64);
  gradient.addColorStop(0, "rgba(70,43,87,.2)");
  gradient.addColorStop(1, "rgba(70,43,87,0)");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, 128, 128);
  const shadowTexture = new THREE.CanvasTexture(shadowCanvas);
  const shadowGeometry = new THREE.PlaneGeometry(WIDTH * 1.5, DEPTH * 1.7);
  const shadowMaterial = new THREE.MeshBasicMaterial({
    map: shadowTexture,
    transparent: true,
    depthWrite: false,
  });
  const shadow = new THREE.Mesh(shadowGeometry, shadowMaterial);
  shadow.rotation.x = -Math.PI / 2;
  shadow.position.set(0.1, -0.2, 0.2);
  scene.add(shadow);
  disposables.push(shadowTexture, shadowGeometry, shadowMaterial);

  const smooth = (x) => (x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x));
  const ramp = (u, from, span) => smooth((u - from) / span);

  function draw() {
    const cycle = Math.floor(time / CYCLE),
      u = (time - cycle * CYCLE) / CYCLE;
    // A different band each cycle: any one row group can be the proven one.
    const band0 = 4 + ((cycle * 11) % (ROWS - BAND - 8));
    const raise = ramp(u, 0.02, 0.12) * (1 - ramp(u, 0.88, 0.1));
    const sweep = ramp(u, 0.16, 0.38);
    const pulseOn = ramp(u, 0.14, 0.04) * (1 - ramp(u, 0.56, 0.05));
    const seal = ramp(u, 0.58, 0.1) * (1 - ramp(u, 0.86, 0.08));
    const px = (sweep - 0.5) * WIDTH;
    const bandZ = (band0 + (BAND - 1) / 2 - (ROWS - 1) / 2) * PITCH;
    let top = BASE;

    for (let r = 0; r < ROWS; r++) {
      const inBand = r >= band0 && r < band0 + BAND;
      const z = (r - (ROWS - 1) / 2) * PITCH;
      for (let c = 0; c < COLS; c++) {
        const i = r * COLS + c,
          x = (c - (COLS - 1) / 2) * PITCH;
        let h =
          BASE +
          Math.sin(x * 1.7 + time * 0.7) * Math.cos(z * 1.9 - time * 0.5) * 0.034 +
          (jitter[i] - 0.5) * 0.018;
        if (inBand) {
          h += 0.15 * raise;
          if (h > top) top = h;
          const passed = smooth((px - x) / 0.25 + 0.5) * Math.max(pulseOn, sweep >= 1 ? 1 : 0);
          const near = Math.exp(-Math.pow((x - px) / 0.3, 2)) * pulseOn;
          color
            .copy(frosted)
            .lerp(lit, raise * (0.42 + 0.58 * Math.max(passed, seal)))
            .lerp(hot, near * 0.85);
        } else {
          color.copy(frosted);
        }
        dummy.position.set(x, 0, z);
        dummy.scale.set(1, h, 1);
        dummy.updateMatrix();
        tiles.setMatrixAt(i, dummy.matrix);
        tiles.setColorAt(i, color);
      }
    }
    tiles.instanceMatrix.needsUpdate = true;
    tiles.instanceColor.needsUpdate = true;

    pulse.position.set(px, top + 0.02, bandZ);
    pulseMaterial.opacity = pulseOn * raise;
    glow.position.set(px, 0.42, bandZ);
    glow.intensity = (5 * pulseOn + 2.2 * seal) * raise;

    const fill = Math.min(1, sweep * 1.15) * raise;
    dotMaterial.opacity = fill;
    for (let k = 0; k < BAND; k++) {
      dummy.position.set(WIDTH / 2 + 0.2, top + 0.02, (band0 + k - (ROWS - 1) / 2) * PITCH);
      const s = 0.35 + 0.65 * fill;
      dummy.scale.set(s, s, s);
      dummy.updateMatrix();
      dots.setMatrixAt(k, dummy.matrix);
    }
    dots.instanceMatrix.needsUpdate = true;

    const rx = WIDTH / 2 + 0.06,
      rz = (BAND * PITCH) / 2 + 0.05,
      ry = top + 0.012;
    railMaterial.opacity = seal * raise;
    const edges = [
      [0, bandZ - rz, 2 * rx, 0],
      [0, bandZ + rz, 2 * rx, 0],
      [-rx, bandZ, 2 * rz, Math.PI / 2],
      [rx, bandZ, 2 * rz, Math.PI / 2],
    ];
    for (let k = 0; k < 4; k++) {
      const [ex, ez, length, rot] = edges[k];
      dummy.position.set(ex, ry, ez);
      dummy.rotation.set(0, rot, 0);
      dummy.scale.set(length, 1, 1);
      dummy.updateMatrix();
      rails.setMatrixAt(k, dummy.matrix);
    }
    dummy.rotation.set(0, 0, 0);
    rails.instanceMatrix.needsUpdate = true;

    rig.rotation.y = -0.55 + Math.sin(time * 0.11) * 0.12 + pointerX * 0.18;
    rig.rotation.x = pointerY * 0.05;
    rig.position.y = Math.sin(time * 0.55) * 0.025;
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
    const distance = camera.aspect < 1 ? 1.45 : camera.aspect < 1.4 ? 1.2 : 1.06;
    camera.position.set(0.25, 3.0 * distance, 4.9 * distance);
    camera.lookAt(0.05, -0.1, 0);
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
    disposables.forEach((d) => d.dispose());
    environment.dispose();
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
