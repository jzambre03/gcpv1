from __future__ import annotations
import argparse, json, re, hashlib, difflib, mimetypes, zipfile
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# -------- Optional exact YAML line numbers (falls back if missing) --------
try:
    from ruamel.yaml import YAML  # precise line/col for YAML
    _HAVE_RUAMEL = True
except Exception:
    _HAVE_RUAMEL = False

# ----------------- Generic helpers -----------------
def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def _load_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

def _is_probably_text(p: Path, sniff_bytes: int = 8192) -> bool:
    try:
        b = p.read_bytes()[:sniff_bytes]
    except Exception:
        return False
    if b"\x00" in b:
        return False
    try:
        b.decode("utf-8")
        return True
    except Exception:
        mt, _ = mimetypes.guess_type(str(p))
        return bool(mt and mt.startswith("text/"))

def _file_type_from_path(p: Path) -> str:
    name = p.name.lower()
    ext = p.suffix.lower()
    parts = [s.lower() for s in p.parts]
    if name == "jenkinsfile" or "jenkinsfile" in name:
        return "ci"
    if name in ("pom.xml","build.gradle","build.gradle.kts","settings.gradle",
                "settings.gradle.kts","package.json","requirements.txt","pyproject.toml","go.mod"):
        return "build"
    if ext in (".yml",".yaml",".json",".toml",".ini",".cfg",".conf",".properties"):
        return "config"
    if ext in (".tf",".tfvars") or "terraform" in parts:
        return "infra"
    if ext in (".sql",".db",".ddl"):
        return "schema"
    if ext in (".java",".py",".go",".ts",".js",".cs",".groovy"):
        return "code"
    return "other"

def _env_tag_from_path(rel: str) -> Optional[str]:
    lower = rel.lower()
    for tag in ("dev","qa","staging","stage","prod","production","vbg","vcg","vbgalpha"):
        if f"-{tag}" in lower or f"/{tag}/" in lower or f"_{tag}." in lower or f"/{tag}-" in lower:
            return "staging" if tag == "stage" else ("prod" if tag=="production" else tag)
    return None

def _to_locator_from_flat(filename: str, key: str) -> Dict[str, Any]:
    ext = Path(filename).suffix.lower()
    if ext in (".yml",".yaml"):
        return {"type": "yamlpath", "value": f"{filename}.{key}" if key else filename}
    if ext == ".json":
        return {"type": "jsonpath", "value": f"{filename}.{key}" if key else filename}
    return {"type": "keypath", "value": f"{filename}.{key}" if key else filename}

# ----------------- Repo scan & classify -----------------
def extract_repo_tree(root: Path) -> List[str]:
    files: List[str] = []
    for p in root.rglob("*"):
        if p.is_file():
            rel_path = str(p.relative_to(root)).replace("\\","/")
            # Skip .git directory and hidden files
            if not rel_path.startswith('.git/') and not rel_path.startswith('.'):
                files.append(rel_path)
    return sorted(files)

def classify_files(root: Path, relpaths: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for rel in relpaths:
        p = (root / rel)
        st = p.stat()
        ft = _file_type_from_path(p)
        out.append({
            "path": rel, "name": p.name, "ext": p.suffix.lower(), "size": st.st_size, "mtime": st.st_mtime,
            "sha256": _sha256_file(p), "file_type": ft, "env_tag": _env_tag_from_path(rel), "module": None
        })
    return out

# ----------------- Structural diff -----------------
def diff_structural(g_files: List[Dict[str, Any]], c_files: List[Dict[str, Any]]) -> Dict[str, Any]:
    gmap = {f["path"]: f for f in g_files}
    cmap = {f["path"]: f for f in c_files}
    added, removed, modified, renamed = [], [], [], []

    for path in cmap.keys() - gmap.keys():
        added.append(path)
    for path in gmap.keys() - cmap.keys():
        removed.append(path)
    for path in cmap.keys() & gmap.keys():
        if gmap[path]["sha256"] != cmap[path]["sha256"]:
            modified.append(path)

    gh, ch = {}, {}
    for f in g_files:
        gh.setdefault(f["sha256"], []).append(f["path"])
    for f in c_files:
        ch.setdefault(f["sha256"], []).append(f["path"])
    for h, g_paths in gh.items():
        c_paths = ch.get(h, [])
        for gp in g_paths:
            for cp in c_paths:
                if gp != cp and gp in removed and cp in added:
                    renamed.append({"from": gp, "to": cp})
                    removed.remove(gp); added.remove(cp)
    return {"added": sorted(added), "removed": sorted(removed), "modified": sorted(modified), "renamed": renamed}

# ----------------- Config parsing & diff -----------------
def _flatten_dict(d: Dict[str, Any], prefix: str="") -> Dict[str, Any]:
    flat = {}
    for k, v in (d or {}).items():
        newk = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            flat.update(_flatten_dict(v, newk))
        else:
            flat[newk] = v
    return flat

def _parse_props_text(txt: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for line in txt.splitlines():
        s=line.strip()
        if not s or s.startswith("#"): continue
        if "=" in s:
            k,v = s.split("=",1); out[k.strip()] = v.strip()
    return out

def _parse_yaml_json_text(txt: str, ext: str) -> Optional[Dict[str, Any]]:
    try:
        import json, yaml  # type: ignore
        if ext == ".json":
            return json.loads(txt)
        if _HAVE_RUAMEL:
            y = YAML(typ="rt")  # keeps line numbers
            return y.load(txt)
        return yaml.safe_load(txt)  # best-effort
    except Exception:
        return None

def _parse_config_file(p: Path) -> Optional[Dict[str, Any]]:
    txt = _load_text(p)
    if txt is None: return None
    ext = p.suffix.lower()
    if ext in (".yml",".yaml",".json"):
        return _parse_yaml_json_text(txt, ext) or {}
    if ext in (".properties",".ini",".cfg",".conf",".toml"):
        return _parse_props_text(txt)
    return None

def semantic_config_diff(g_root: Path, c_root: Path, changed_paths: List[str]) -> Dict[str, Dict[str, Any]]:
    added, removed, changed = {}, {}, {}
    for rel in changed_paths:
        # DEDUPLICATION FIX: Skip Spring application files (handled by detector_spring_profiles)
        # This prevents duplicate deltas for the same configuration changes
        rel_lower = rel.lower()
        if ('application' in rel_lower and 
            (rel_lower.endswith('.yml') or rel_lower.endswith('.yaml') or rel_lower.endswith('.properties'))):
            # Skip files like: application.yml, application-*.yml, application-dev.properties, etc.
            # These will be processed by detector_spring_profiles() which provides better metadata
            continue
        
        p_g = g_root / rel
        p_c = c_root / rel
        # Exclude .json files from semantic config diff as per requirement
        if p_c.suffix.lower() not in (".yml",".yaml",".properties",".toml",".ini",".cfg",".conf"):
            continue
        def parse_any(p: Path) -> Optional[Dict[str, Any]]:
            return _parse_config_file(p)
        g_obj = parse_any(p_g) if p_g.exists() else None
        c_obj = parse_any(p_c) if p_c.exists() else None
        g_flat = _flatten_dict(g_obj or {}); c_flat = _flatten_dict(c_obj or {})
        g_keys, c_keys = set(g_flat), set(c_flat)
        for k in sorted(c_keys - g_keys):
            added[f"{rel}.{k}"] = c_flat[k]
        for k in sorted(g_keys - c_keys):
            removed[f"{rel}.{k}"] = g_flat[k]
        for k in sorted(c_keys & g_keys):
            if c_flat[k] != g_flat[k]:
                changed[f"{rel}.{k}"] = {"from": g_flat[k], "to": c_flat[k]}
    return {"added": added, "removed": removed, "changed": changed}

# ----------------- Dependency extraction & diff -----------------
def extract_dependencies(root: Path) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    # Maven (simple)
    pom = root / "pom.xml"
    if pom.exists():
        txt = pom.read_text(encoding="utf-8", errors="ignore")
        deps = re.findall(r"<dependency>\s*<groupId>(.*?)</groupId>\s*<artifactId>(.*?)</artifactId>\s*(?:<version>(.*?)</version>)?", txt, re.S)
        out["maven"] = {"all": {f"{g}:{a}": (v or "").strip() for g,a,v in deps}}
    # NPM
    pkg = root / "package.json"
    if pkg.exists():
        try:
            obj = json.loads(pkg.read_text(encoding="utf-8"))
            dd = {**(obj.get("dependencies") or {}), **(obj.get("devDependencies") or {})}
            out["npm"] = {"all": dd}
        except Exception:
            pass
    # Python
    req = root / "requirements.txt"
    if req.exists():
        dd = {}
        for line in req.read_text(encoding="utf-8", errors="ignore").splitlines():
            s=line.strip()
            if not s or s.startswith("#"): continue
            if "==" in s:
                k,v = s.split("==",1); dd[k.strip()] = v.strip()
            else:
                dd[s]= ""
        out["pip"] = {"all": dd}
    return out

def dependency_diff(g_deps: Dict[str, Dict[str, Any]], c_deps: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    diff: Dict[str, Any] = {}
    ecosystems = set(g_deps.keys()) | set(c_deps.keys())
    for eco in ecosystems:
        g = (g_deps.get(eco) or {}).get("all", {})
        c = (c_deps.get(eco) or {}).get("all", {})
        added = {k:v for k,v in c.items() if k not in g}
        removed = {k:v for k,v in g.items() if k not in c}
        changed = {k: {"from": g[k], "to": c[k]} for k in g.keys() & c.keys() if g[k] != c[k]}
        diff[eco] = {"added": added, "removed": removed, "changed": changed}
    return diff

# ----------------- Detectors: Spring Profiles & Jenkinsfile -----------------
def detector_spring_profiles(g_root: Path, c_root: Path) -> List[Dict[str, Any]]:
    def collect(root: Path) -> Dict[str, Dict[str, Any]]:
        collected: Dict[str, Dict[str, Any]] = {}
        for pattern in ("**/application*.yml","**/application*.yaml","**/application*.properties"):
            for p in root.rglob(pattern):
                rel = str(p.relative_to(root)).replace("\\","/")
                collected[rel] = _parse_config_file(p) or {}
        return collected
    g = collect(g_root); c = collect(c_root)
    deltas: List[Dict[str, Any]] = []
    all_files = sorted(set(g.keys()) | set(c.keys()))
    for rel in all_files:
        g_obj = g.get(rel, {}); c_obj = c.get(rel, {})
        g_flat = _flatten_dict(g_obj or {}); c_flat = _flatten_dict(c_obj or {})
        g_keys, c_keys = set(g_flat), set(c_flat)
        for k in sorted(c_keys - g_keys):
            deltas.append({"id": f"spring+{rel}.{k}","category":"spring_profile","file": rel,
                           "locator": _to_locator_from_flat(rel, k), "old": None, "new": c_flat[k]})
        for k in sorted(g_keys - c_keys):
            deltas.append({"id": f"spring-{rel}.{k}","category":"spring_profile","file": rel,
                           "locator": _to_locator_from_flat(rel, k), "old": g_flat[k], "new": None})
        for k in sorted(c_keys & g_keys):
            if c_flat[k] != g_flat[k]:
                deltas.append({"id": f"spring~{rel}.{k}","category":"spring_profile","file": rel,
                               "locator": _to_locator_from_flat(rel, k), "old": g_flat[k], "new": c_flat[k]})
    # add rough line numbers by searching the key in text (heuristic)
    for d in deltas:
        f = c_root / d["file"]
        txt = _load_text(f) if f.exists() else None
        if txt:
            needle = d["locator"]["value"].split(".",1)[-1] if "." in d["locator"]["value"] else d["locator"]["value"]
            line = next((i+1 for i,ln in enumerate(txt.splitlines()) if needle.split(".")[0] in ln), None)
            if line: d["locator"]["line_start"] = line
    return deltas

def _summarize_jenkinsfile(p: Path) -> Dict[str, Any]:
    txt = _load_text(p) or ""
    out: Dict[str, Any] = {}
    m = re.search(r"agent\s+([a-zA-Z_][a-zA-Z0-9_]*)", txt);           out["agent.kind"] = m.group(1) if m else None
    m2 = re.search(r"label\s*[:=]\s*['\"]([^'\"]+)['\"]", txt);        out["agent.label"] = m2.group(1) if m2 else None
    img = re.search(r"docker\s*\{\s*image\s+['\"]([^'\"]+)['\"]", txt, re.S)
    out["agent.docker.image"] = img.group(1) if img else None
    creds = re.findall(r"credentialsId\s*[:=]\s*['\"]([^'\"]+)['\"]", txt); out["credentials.ids"] = list(dict.fromkeys(creds)) if creds else None
    libs = re.findall(r"@Library\(['\"]([^'\"]+)['\"]\)", txt);            out["libraries"] = libs or None
    stages = re.findall(r"stage\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", txt);    out["stages"] = stages or None
    whens = len(re.findall(r"\bwhen\s*\{", txt));                           out["when.blocks"] = whens or None
    return {k:v for k,v in out.items() if v is not None}

def detector_jenkinsfile(g_root: Path, c_root: Path) -> List[Dict[str, Any]]:
    g_file = g_root/"Jenkinsfile"; c_file = c_root/"Jenkinsfile"
    if not g_file.exists() and not c_file.exists(): return []
    g = _summarize_jenkinsfile(g_file) if g_file.exists() else {}
    c = _summarize_jenkinsfile(c_file) if c_file.exists() else {}
    keys = sorted(set(g.keys()) | set(c.keys()))
    deltas: List[Dict[str, Any]] = []
    rel = "Jenkinsfile"; txt = _load_text(c_file) or ""
    for k in keys:
        gv, cv = g.get(k), c.get(k)
        if gv != cv:
            loc = {"type":"keypath","value": f"{rel}.{k}"}
            token = k.split(".")[-1]
            line = next((i+1 for i,ln in enumerate(txt.splitlines()) if token in ln), None)
            if line: loc["line_start"] = line
            deltas.append({"id": f"jenkins~{k}", "category":"jenkins", "file": rel,
                           "locator": loc, "old": gv, "new": cv})
    return deltas

# ----------------- Code hunk diff (line-precise) -----------------
def _hunks_for_file(g_path: Path, c_path: Path, rel: str, max_hunks: int = 200) -> List[Dict[str, Any]]:
    a = (_load_text(g_path) or "").splitlines()
    b = (_load_text(c_path) or "").splitlines()
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    hunks: List[Dict[str, Any]] = []
    count = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal": continue
        if count >= max_hunks: break
        snippet = "\n".join(difflib.unified_diff(a[i1-2 if i1>=2 else 0:i2+2],
                                                 b[j1-2 if j1>=2 else 0:j2+2],
                                                 fromfile="golden/"+rel, tofile="candidate/"+rel, lineterm=""))
        hunks.append({
            "id": f"hunk:{rel}:{i1}-{i2}->{j1}-{j2}",
            "category": "code_hunk",
            "file": rel,
            "locator": {
                "type": "unidiff",
                "value": f"{rel}#{i1+1}-{i2}-{j1+1}-{j2}",
                "old_start": i1+1, "old_lines": max(0, i2-i1),
                "new_start": j1+1, "new_lines": max(0, j2-j1)
            },
            "old": "\n".join(a[i1:i2][:20]),
            "new": "\n".join(b[j1:j2][:20]),
            "snippet": snippet[:2000]
        })
        count += 1
    return hunks

def build_code_hunk_deltas(g_root: Path, c_root: Path, modified_paths: List[str]) -> List[Dict[str, Any]]:
    deltas: List[Dict[str, Any]] = []
    for rel in modified_paths:
        gp, cp = g_root/rel, c_root/rel
        if not gp.exists() or not cp.exists(): continue
        if not _is_probably_text(cp): continue
        deltas.extend(_hunks_for_file(gp, cp, rel))
    return deltas

# ----------------- Binary & archive deltas -----------------
def build_binary_deltas(g_root: Path, c_root: Path, modified_paths: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for rel in modified_paths:
        gp, cp = g_root/rel, c_root/rel
        if not gp.exists() or not cp.exists(): continue
        if _is_probably_text(cp): continue  # text handled by code hunks

        # Generic binary metadata
        gsize, csize = gp.stat().st_size, cp.stat().st_size
        gsha, csha = _sha256_file(gp), _sha256_file(cp)
        out.append({
            "id": f"bin~{rel}",
            "category": "binary_meta",
            "file": rel,
            "locator": {"type": "path", "value": rel},
            "old": {"size": gsize, "sha256": gsha},
            "new": {"size": csize, "sha256": csha}
        })

        # ZIP/JAR/WAR entry diff + MANIFEST keys
        if zipfile.is_zipfile(gp) and zipfile.is_zipfile(cp):
            def entries(p: Path) -> Dict[str, int]:
                with zipfile.ZipFile(p) as z:
                    return {i.filename: i.file_size for i in z.infolist()}
            ge, ce = entries(gp), entries(cp)
            added = {k: ce[k] for k in ce.keys() - ge.keys()}
            removed = {k: ge[k] for k in ge.keys() - ce.keys()}
            changed = {k: {"from": ge[k], "to": ce[k]} for k in ge.keys() & ce.keys() if ge[k] != ce[k]}
            if added or removed or changed:
                out.append({
                    "id": f"zip~{rel}",
                    "category": "archive_delta",
                    "file": rel,
                    "locator": {"type": "path", "value": rel},
                    "old": {"entries": len(ge)},
                    "new": {"entries": len(ce)},
                    "diff": {"added": added, "removed": removed, "changed": changed}
                })
            def manifest_map(p: Path) -> Dict[str, str]:
                try:
                    with zipfile.ZipFile(p) as z:
                        with z.open("META-INF/MANIFEST.MF") as mf:
                            txt = mf.read().decode("utf-8", "ignore")
                            m = {}
                            for line in txt.splitlines():
                                if ":" in line:
                                    k,v = line.split(":",1)
                                    m[k.strip()] = v.strip()
                            return m
                except Exception:
                    return {}
            gm, cm = manifest_map(gp), manifest_map(cp)
            if gm or cm:
                keys = set(gm) | set(cm)
                for k in sorted(keys):
                    if gm.get(k) != cm.get(k):
                        out.append({
                            "id": f"manifest~{rel}.{k}",
                            "category": "archive_manifest",
                            "file": rel,
                            "locator": {"type":"keypath","value": f"{rel}.MANIFEST.{k}"},
                            "old": gm.get(k), "new": cm.get(k)
                        })
    return out

# ----------------- Policies & Evidence -----------------
def _policy_load(policies_path: Optional[Path]) -> Dict[str, Any]:
    if not policies_path or not policies_path.exists():
        return {}
    try:
        import yaml  # type: ignore
        return yaml.safe_load(policies_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}

def _policy_tag(delta: Dict[str, Any], policies: Dict[str, Any]) -> Dict[str, Any]:
    tag, reason = "suspect", ""
    env_allow = set(str(x).lower() for x in (policies.get("env_allow_keys") or []))
    loc_val = (delta.get("locator") or {}).get("value","").lower()
    if any(tok in loc_val for tok in env_allow):
        tag, reason = "allowed_variance", "env_allow_keys"
    for inv in (policies.get("invariants") or []):
        lc = str(inv.get("locator_contains","")).lower()
        if lc and lc in loc_val:
            forbid = set(inv.get("forbid_values", []))
            if delta.get("new") in forbid:
                tag, reason = "invariant_breach", inv.get("name","invariant")
    delta["policy"] = {"tag": tag, "rule": reason}
    return delta

def _load_evidence(evidence_path: Optional[Path]) -> List[Dict[str, Any]]:
    if not evidence_path: return []
    try:
        arr = json.loads(evidence_path.read_text(encoding="utf-8"))
        return arr if isinstance(arr, list) else []
    except Exception:
        return []

# ----------------- Bundle build -----------------
def _build_deltas(conf_diff: Dict[str, Any], dep_diff: Dict[str, Any], file_changes: Dict[str, Any]) -> List[Dict[str, Any]]:
    deltas: List[Dict[str, Any]] = []
    for k,v in (conf_diff.get("added") or {}).items():
        filename, key = k.split(".",1) if "." in k else (k, "")
        deltas.append({"id": f"cfg+{k}", "category":"config", "file": filename,
                       "locator": _to_locator_from_flat(filename, key), "old": None, "new": v})
    for k,v in (conf_diff.get("removed") or {}).items():
        filename, key = k.split(".",1) if "." in k else (k, "")
        deltas.append({"id": f"cfg-{k}", "category":"config", "file": filename,
                       "locator": _to_locator_from_flat(filename, key), "old": v, "new": None})
    for k,ch in (conf_diff.get("changed") or {}).items():
        filename, key = k.split(".",1) if "." in k else (k, "")
        deltas.append({"id": f"cfg~{k}", "category":"config", "file": filename,
                       "locator": _to_locator_from_flat(filename, key), "old": ch.get("from"), "new": ch.get("to")})
    for eco, dd in (dep_diff or {}).items():
        for name, ver in (dd.get("added") or {}).items():
            deltas.append({"id": f"dep+{eco}:{name}", "category":"dependency", "file": eco,
                           "locator": {"type":"coord","value": f"{eco}:{name}"}, "old": None, "new": ver})
        for name, ver in (dd.get("removed") or {}).items():
            deltas.append({"id": f"dep-{eco}:{name}", "category":"dependency", "file": eco,
                           "locator": {"type":"coord","value": f"{eco}:{name}"}, "old": ver, "new": None})
        for name, ch in (dd.get("changed") or {}).items():
            deltas.append({"id": f"dep~{eco}:{name}", "category":"dependency", "file": eco,
                           "locator": {"type":"coord","value": f"{eco}:{name}"}, "old": ch.get("from"), "new": ch.get("to")})
    for rel in file_changes.get("added", []):
        deltas.append({"id": f"file+{rel}", "category":"file", "file": rel,
                       "locator": {"type":"path","value": rel}, "old": None, "new": "present"})
    for rel in file_changes.get("removed", []):
        deltas.append({"id": f"file-{rel}", "category":"file", "file": rel,
                       "locator": {"type":"path","value": rel}, "old": "present", "new": None})
    for rn in file_changes.get("renamed", []):
        oldp, newp = rn.get("from"), rn.get("to")
        deltas.append({"id": f"file~{oldp}->{newp}", "category":"file", "file": newp,
                       "locator": {"type":"path","value": newp}, "old": oldp, "new": newp})
    return deltas

def emit_context_bundle(out_dir: Path,
                        golden: Path,
                        candidate: Path,
                        overview: Dict[str, Any],
                        dep_diff: Dict[str, Any],
                        conf_diff: Dict[str, Any],
                        file_changes: Dict[str, Any],
                        extra_deltas: Optional[List[Dict[str, Any]]] = None,
                        policies_path: Optional[Path] = None,
                        evidence: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    policies = _policy_load(policies_path)
    deltas = _build_deltas(conf_diff, dep_diff, file_changes)
    if extra_deltas: deltas.extend(extra_deltas)
    tagged = [_policy_tag(d.copy(), policies) for d in deltas]
    bundle = {
        "meta": {"golden": str(golden), "candidate": str(candidate), "generated_at": datetime.utcnow().isoformat() + "Z"},
        "overview": overview or {},
        "file_changes": file_changes or {},
        "dependencies": dep_diff or {},
        "configs": {"diff": conf_diff or {}, "environment_keys": [], "possible_secrets": []},
        "deltas": tagged,
        "evidence": evidence or [],
        "clusters": [],
        "patches": []
    }
    (out_dir/"context_bundle.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    return bundle

# ----------------- Main -----------------
def main():
    ap = argparse.ArgumentParser(description="Drift context generator (Golden vs Candidate) — line-precise, config-aware, binary-aware.")
    ap.add_argument("--golden", required=True, help="Path to golden repo directory")
    ap.add_argument("--candidate", required=True, help="Path to candidate repo directory")
    ap.add_argument("--out", required=True, help="Output directory")
    ap.add_argument("--policies", default=None, help="Optional policies.yaml path")
    ap.add_argument("--evidence", default=None, help="Optional evidence.json path (list of {tool, ok, detail})")
    args = ap.parse_args()

    g_root = Path(args.golden).resolve()
    c_root = Path(args.candidate).resolve()
    out_dir = Path(args.out).resolve(); out_dir.mkdir(parents=True, exist_ok=True)

    g_paths = extract_repo_tree(g_root); c_paths = extract_repo_tree(c_root)
    g_files = classify_files(g_root, g_paths); c_files = classify_files(c_root, c_paths)

    overview = {
        "golden_files": len(g_files),
        "candidate_files": len(c_files),
        "languages_hint": sorted({f["ext"] for f in c_files if f["file_type"] == "code"}),
        "ci_present": any("jenkinsfile" in f["name"].lower() for f in c_files),
        "build_tools": [f["name"] for f in c_files if f["file_type"] == "build"][:10]
    }
    (out_dir/"repo_overview.json").write_text(json.dumps(overview, indent=2), encoding="utf-8")

    file_changes = diff_structural(g_files, c_files)
    (out_dir/"file_changes.json").write_text(json.dumps(file_changes, indent=2), encoding="utf-8")

    g_deps = extract_dependencies(g_root); c_deps = extract_dependencies(c_root)
    dep_diff = dependency_diff(g_deps, c_deps)
    (out_dir/"dependency_diff.json").write_text(json.dumps(dep_diff, indent=2), encoding="utf-8")

    changed_paths = sorted(set(file_changes["modified"]) | set(file_changes["added"]))
    conf_diff = semantic_config_diff(g_root, c_root, changed_paths)
    (out_dir/"config_diff.json").write_text(json.dumps(conf_diff, indent=2), encoding="utf-8")

    # detectors
    spring_deltas = detector_spring_profiles(g_root, c_root)
    jenkins_deltas = detector_jenkinsfile(g_root, c_root)

    # line-precise code hunks & binary/archive deltas
    code_hunks = build_code_hunk_deltas(g_root, c_root, file_changes.get("modified", []))
    binary_deltas = build_binary_deltas(g_root, c_root, file_changes.get("modified", []))

    # evidence
    evidence_path = Path(args.evidence).resolve() if args.evidence else None
    evidence = _load_evidence(evidence_path)

    # emit
    policies_path = Path(args.policies).resolve() if args.policies else None
    extra = spring_deltas + jenkins_deltas + code_hunks + binary_deltas
    emit_context_bundle(out_dir, g_root, c_root, overview, dep_diff, conf_diff, file_changes,
                        extra_deltas=extra, policies_path=policies_path, evidence=evidence)

    print(json.dumps({"out_dir": str(out_dir),
                      "artifacts": [str(p.name) for p in out_dir.iterdir() if p.is_file()]}, indent=2))

if __name__ == "__main__":
    main()
