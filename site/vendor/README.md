# Browser libraries

These files are committed source inputs. `build_site.py` verifies their SHA-256 hashes and byte counts in `manifest.json`, then embeds both scripts and their license notices into the page. The ordinary build does not download or regenerate them. No CDN script or dynamic module import is used at runtime.

- snarkjs 0.7.5: exact `build/snarkjs.min.js` from the fork's npm lockfile installation; GPL-3.0 license included.
- Three.js 0.180.0: the exports in `site/three-entry.js`, bundled as an IIFE by esbuild 0.25.10; MIT license included. The decoration still runs in the page's trust boundary.

Explicit maintenance workflow, from the repo root:

```sh
npm ci --prefix code/llama.cpp/examples/receipts/zk/groth16
npm ci --prefix site --ignore-scripts
npm run vendor --prefix site
python3 checks/check_site_supply.py
python3 site/build_site.py
```

Review and commit the lockfile, bundle and digest changes together. npm lockfiles pin package tarballs with integrity values. A digest committed alongside a library prevents accidental or isolated file substitution; it does not protect against compromise of the repository, deployment origin, or a maintainer who can replace both. The five Pages action commits were resolved through their official GitHub repositories before pinning.
