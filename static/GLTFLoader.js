/* GLTFLoader for three.js r160 — minimal embedded version for .glb files. */
import * as THREE from './three.module.min.js?v=2';

const GLTFLoader = (function () {
  class GLTFLoader {
    constructor(manager) { this.manager = manager || THREE.DefaultLoadingManager; }
    async loadAsync(url, onLoad, onProgress, onError) {
      try {
        const h = { 'Accept': 'model/gltf-binary' };
        const t = window.__SESSION_TOKEN__;
        if (t) h['x-session-token'] = t;
        const resp = await fetch(url, { headers: h });
        if (!resp.ok) throw new Error('HTTP ' + resp.status + ' for ' + url);
        const buf = await resp.arrayBuffer();
        const gltf = this.parse(buf);
        if (onLoad) onLoad(gltf);
        return gltf;
      } catch (e) {
        if (onError) onError(e);
        throw e;
      }
    }
    parse(data) {
      // GLB: 12-byte header + JSON chunk + BIN chunk
      const dv = new DataView(data);
      if (dv.getUint32(0, true) !== 0x46546C67) throw new Error('Not a GLB file');
      const version = dv.getUint32(4, true);
      const length = dv.getUint32(8, true);
      let offset = 12;
      let json = null, bin = null;
      while (offset < length) {
        const chunkLen = dv.getUint32(offset, true);
        const chunkType = dv.getUint32(offset + 4, true);
        if (chunkType === 0x4E4F534A) { // JSON
          json = new TextDecoder().decode(new Uint8Array(data, offset + 8, chunkLen));
        } else if (chunkType === 0x004E4942) { // BIN
          bin = data.slice(offset + 8, offset + 8 + chunkLen);
        }
        offset += 8 + chunkLen;
      }
      if (!json) throw new Error('No JSON chunk in GLB');
      const g = JSON.parse(json);
      return { scene: this._buildScene(g, bin), scenes: g.scenes || [], animations: g.animations || [] };
    }
    _buildScene(g, bin) {
      const scene = new THREE.Group();
      const _scene = (g.scenes && g.scenes[0]) || g.scene;
      const nodes = (g.nodes || []).map(n => {
        const obj = new THREE.Group();
        if (n.name) obj.name = n.name;
        if (n.translation) obj.position.fromArray(n.translation);
        if (n.rotation) obj.quaternion.fromArray(n.rotation);
        if (n.scale) obj.scale.fromArray(n.scale);
        if (n.mesh != null && g.meshes) {
          const meshDef = g.meshes[n.mesh];
          if (meshDef) {
            const prim = meshDef.primitives[0];
            if (prim && g.accessors) {
              const posAcc = g.accessors[prim.attributes.POSITION];
              if (posAcc) {
                const geo = new THREE.BufferGeometry();
                const posData = this._getAccessorData(posAcc, bin, 3);
                geo.setAttribute('position', new THREE.Float32BufferAttribute(posData, 3));
                if (prim.attributes.NORMAL != null) {
                  const nrmAcc = g.accessors[prim.attributes.NORMAL];
                  if (nrmAcc) {
                    const nrmData = this._getAccessorData(nrmAcc, bin, 3);
                    geo.setAttribute('normal', new THREE.Float32BufferAttribute(nrmData, 3));
                  }
                }
                if (prim.attributes.TEXCOORD_0 != null) {
                  const uvAcc = g.accessors[prim.attributes.TEXCOORD_0];
                  if (uvAcc) {
                    const uvData = this._getAccessorData(uvAcc, bin, 2);
                    geo.setAttribute('uv', new THREE.Float32BufferAttribute(uvData, 2));
                  }
                }
                if (prim.indices != null) {
                  const idxAcc = g.accessors[prim.indices];
                  if (idxAcc) {
                    const idxData = this._getAccessorData(idxAcc, bin, 1, true);
                    geo.setIndex(new THREE.BufferAttribute(idxData, 1));
                  }
                }
                geo.computeVertexNormals();
                const mat = this._buildMaterial(prim, g, bin);
                const mesh = new THREE.Mesh(geo, mat);
                obj.add(mesh);
              }
            }
          }
        }
        return obj;
      });
      for (const childIdx of (_scene.nodes || [])) {
        if (nodes[childIdx]) scene.add(nodes[childIdx]);
      }
      return scene;
    }
    _getAccessorData(acc, bin, itemSize, isIndex) {
      if (!bin) return new Float32Array(0);
      const dv = new DataView(bin);
      const byteOffset = acc.byteOffset || 0;
      const count = acc.count;
      const type = acc.componentType;
      if (type === 5126) { // FLOAT
        return new Float32Array(bin, byteOffset, count * itemSize);
      } else if (type === 5123) { // UNSIGNED_SHORT
        return isIndex ? new Uint16Array(bin, byteOffset, count) : new Float32Array(count * itemSize);
      } else if (type === 5125) { // UNSIGNED_INT
        return isIndex ? new Uint32Array(bin, byteOffset, count) : new Float32Array(count * itemSize);
      }
      return new Float32Array(count * itemSize);
    }
    _buildMaterial(prim, g, bin) {
      const mat = new THREE.MeshLambertMaterial({ color: 0xcccccc });
      if (prim.material != null && g.materials) {
        const md = g.materials[prim.material];
        if (md) {
          if (md.pbrMetallicRoughness && md.pbrMetallicRoughness.baseColorFactor) {
            const c = md.pbrMetallicRoughness.baseColorFactor;
            mat.color = new THREE.Color(c[0], c[1], c[2]);
          }
          if (md.doubleSided) mat.side = THREE.DoubleSide;
        }
      }
      return mat;
    }
  }
  return GLTFLoader;
})();

export { GLTFLoader };
