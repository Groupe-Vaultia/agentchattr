/* G5 — Vue 3D de la progression (three.js embarqué, pas de CDN).
   Charge les .glb par la route A1, les place dans le repère du véhicule,
   colore par statut, affiche les fantômes, et ouvre la fiche au clic.
   Repère CAO : X vers l'arrière, Y latéral, Z vertical.
   Repère three.js : Y_up → on fait x→x, z→y, y→z. */
import * as THREE from './three.module.min.js';
import { OrbitControls } from './OrbitControls.js';
import { GLTFLoader } from './GLTFLoader.js';

const COULEURS = {
  a_concevoir: 0xb0b8c4,
  concue:      0x1f6feb,
  a_commander: 0x888888,
  commandee:   0x1f6feb,
  recue:       0x2da44e,
  fabriquee:   0x2da44e,
  validee:     0x2da44e,
  rejetee:     0xff6b6b,
};
const FANTOME_COLOR = 0x9aa5b1;
const FANTOME_OPACITY = 0.18;

// Repère du véhicule (de maillage.py)
const VEH = { xMin: -200, xMax: 1800, yMin: -500, yMax: 900, zMin: -500, zMax: 700 };

/**
 * Crée la vue 3D dans un conteneur DOM.
 * @param {HTMLElement} conteneur - élément qui recevra le canvas
 * @param {Function} onClicPiece - callback(pieceId, numero, nom)
 * @returns {object} API: charger(pieces, fantomes), resize(), setEclate(v), creerLegende(el), destroy()
 */
export function creerVue3D(conteneur, onClicPiece) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x1a1e24);

  const camera = new THREE.PerspectiveCamera(50, 1, 1, 10000);
  camera.position.set(2200, -1800, 1400);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.domElement.style.cssText = 'width:100%;height:100%;display:block;cursor:grab';
  conteneur.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(700, 100, 0);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;

  // Lumières
  scene.add(new THREE.AmbientLight(0xffffff, 0.5));
  const dir1 = new THREE.DirectionalLight(0xffffff, 0.9);
  dir1.position.set(1, 1.2, 0.8).normalize();
  scene.add(dir1);
  const dir2 = new THREE.DirectionalLight(0xffffff, 0.3);
  dir2.position.set(-1, -0.5, 0.5).normalize();
  scene.add(dir2);

  // Grille au sol (au niveau zMin du véhicule)
  const grid = new THREE.GridHelper(3000, 30, 0x333333, 0x252525);
  grid.position.y = 0; // three.js Y = CAO Z
  scene.add(grid);

  const loader = new GLTFLoader();
  const objets = [];
  const fantomes = [];

  function couleurStatut(statut) {
    return COULEURS[statut] ?? 0x888888;
  }

  // Repère CAO (x,y,z) → three.js après rotation -90° autour de X : (x,z,-y)
  function caoToThree(x, y, z) {
    return new THREE.Vector3(x, z, -y);
  }

  function creerFantome(nom, bbox) {
    const { xMin, xMax, yMin, yMax, zMin, zMax } = bbox;
    const w = xMax - xMin, d = yMax - yMin, h = zMax - zMin;
    const geo = new THREE.BoxGeometry(w, d, h);
    const mat = new THREE.MeshLambertMaterial({
      color: FANTOME_COLOR, transparent: true, opacity: FANTOME_OPACITY,
    });
    const mesh = new THREE.Mesh(geo, mat);
    // Même repère que les GLB : CAO → three via rotation -90° X
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.set((xMin + xMax) / 2, (zMin + zMax) / 2, (yMin + yMax) / 2);
    mesh.userData = { fantome: true, nom };
    scene.add(mesh);
    fantomes.push(mesh);
  }

  async function chargerGLB(url, piece) {
    try {
      const gltf = await loader.loadAsync(url);
      const root = gltf.scene;
      // Le GLB est déjà dans le repère CAO (x, y, z).
      // three.js attend Y_up → on tourne le groupe de -90° autour de X.
      root.rotation.x = -Math.PI / 2;
      const col = couleurStatut(piece.statut);
      root.traverse(child => {
        if (child.isMesh) {
          child.material = new THREE.MeshLambertMaterial({ color: col });
          child.userData.pieceId = piece.id;
          child.userData.numero = piece.numero;
          child.userData.nom = piece.nom;
        }
      });
      scene.add(root);
      objets.push({ root, pieceId: piece.id, numero: piece.numero, statut: piece.statut });
      return true;
    } catch (e) {
      console.warn('G5: échec GLB', url, e);
      return false;
    }
  }

  // Boîte grise de repli (fichier GLB absent)
  function creerBoiteRepli(piece, bbox) {
    const b = bbox || { xMin: 0, xMax: 100, yMin: 0, yMax: 100, zMin: 0, zMax: 100 };
    const w = b.xMax - b.xMin, h = b.zMax - b.zMin, d = b.yMax - b.yMin;
    const geo = new THREE.BoxGeometry(w, h, d);
    const mat = new THREE.MeshLambertMaterial({
      color: 0x666666, transparent: true, opacity: 0.6,
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.copy(caoToThree((b.xMin + b.xMax) / 2, (b.yMin + b.yMax) / 2, (b.zMin + b.zMax) / 2));
    mesh.userData = { pieceId: piece.id, numero: piece.numero, nom: piece.nom };

    // Numéro en sprite au-dessus de la boîte
    const c2 = document.createElement('canvas');
    c2.width = 256; c2.height = 64;
    const ctx = c2.getContext('2d');
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 36px monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(piece.numero || '?', 128, 32);
    const tex = new THREE.CanvasTexture(c2);
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true }));
    sprite.scale.set(80, 20, 1);
    sprite.position.set(0, h / 2 + 15, 0);
    mesh.add(sprite);

    scene.add(mesh);
    objets.push({ root: mesh, pieceId: piece.id, numero: piece.numero, statut: piece.statut, repli: true });
  }

  async function chargerTout(piecesListe, fantomesListe) {
    // Fantômes d'abord (en dessous)
    for (const f of (fantomesListe || [])) {
      creerFantome(f.nom, f.bbox);
    }
    // Pièces
    for (const p of (piecesListe || [])) {
      if (p.fichier_glb) {
        const ok = await chargerGLB(p.fichier_glb, p);
        if (!ok && p.bbox) creerBoiteRepli(p, p.bbox);
      } else if (p.bbox) {
        creerBoiteRepli(p, p.bbox);
      }
    }
    recadrer();
  }

  function recadrer() {
    const box = new THREE.Box3();
    scene.traverse(o => { if (o.isMesh) box.expandByObject(o); });
    if (box.isEmpty()) return;
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z) || 1;
    const dist = maxDim / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)));
    camera.position.copy(center).add(new THREE.Vector3(dist * 0.7, dist * 0.5, -dist * 0.7));
    controls.target.copy(center);
  }

  // Clic → fiche pièce
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  renderer.domElement.addEventListener('click', e => {
    if (e.target !== renderer.domElement) return;
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster.intersectObjects(scene.children, true);
    for (const hit of hits) {
      let obj = hit.object;
      while (obj && obj.userData.pieceId == null) obj = obj.parent;
      if (obj && obj.userData.pieceId != null) {
        if (onClicPiece) onClicPiece(obj.userData.pieceId, obj.userData.numero, obj.userData.nom);
        return;
      }
    }
  });

  // Curseur d'éclaté (placeholder, viendra ensuite)
  let eclate = 0;
  function setEclate(v) { eclate = Math.max(0, Math.min(1, v)); }

  function resize() {
    const w = conteneur.clientWidth || 800;
    const h = conteneur.clientHeight || 500;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  }
  resize();
  const ro = new ResizeObserver(resize);
  ro.observe(conteneur);

  // Boucle de rendu
  let running = true;
  function loop() {
    if (!running) return;
    requestAnimationFrame(loop);
    controls.update();
    renderer.render(scene, camera);
  }
  loop();

  function creerLegende(parentEl) {
    const leg = document.createElement('div');
    leg.className = 'v3d-legende';
    leg.innerHTML =
      '<span class="v3d-li"><i style="background:#1f6feb"></i>conçue</span>' +
      '<span class="v3d-li"><i style="background:#2da44e"></i>validée</span>' +
      '<span class="v3d-li"><i style="background:#b0b8c4"></i>à concevoir</span>' +
      '<span class="v3d-li"><i style="background:#9aa5b1;opacity:.3"></i>fantôme</span>';
    parentEl.appendChild(leg);
    return leg;
  }

  return {
    charger: chargerTout,
    resize,
    setEclate,
    creerLegende,
    destroy() {
      running = false;
      ro.disconnect();
      renderer.dispose();
      conteneur.innerHTML = '';
    },
  };
}


// Enregistrement global pour atelier.js (script non-module)
window.creerVue3D = creerVue3D;
