#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, re, subprocess, sys, hashlib, difflib, mimetypes, zipfile, tarfile, xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

# -------- Optional parsers --------
try:
    from ruamel.yaml import YAML
    _HAVE_RUAMEL = True
except Exception:
    _HAVE_RUAMEL = False

try:
    import tomllib as _toml  # py311+
except Exception:
    try:
        import tomli as _toml  # py310-
    except Exception:
        _toml = None

# -------- Utilities --------
def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()

def _load_text(p: Path) -> Optional[str]:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

def _is_text(p: Path, sniff: int = 8192) -> bool:
    try:
        b = p.read_bytes()[:sniff]
    except Exception:
        return False
    if b"\x00" in b:
        return False
    try:
        b.decode("utf-8"); return True
    except Exception:
        mt, _ = mimetypes.guess_type(str(p))
        return bool(mt and mt.startswith("text/"))

def _have_git() -> bool:
    try:
        subprocess.run(["git", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:
        return False

def _file_type(p: Path) -> str:
    name = p.name.lower(); ext = p.suffix.lower()
    parts = [s.lower() for s in p.parts]
    if name.startswith("jenkinsfile"): return "ci"
    if name in ("pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts",
                "requirements.txt", "pyproject.toml", "go.mod"): return "build"
    # Exclude .json files from config classification as per requirement
    if ext in (".yml",".yaml",".toml",".ini",".cfg",".conf",".properties",".config",".xml"): return "config"
    if ext in (".tf",".tfvars") or "terraform" in parts: return "infra"
    if ext in (".sql",".db",".ddl"): return "schema"
    if ext in (".java",".py",".go",".ts",".js",".json",".cs",".groovy",".kts",".gradle",".sh",".bat",".ps1",".rb",".php",
               ".c",".cpp",".h",".hpp",".html",".css",".md",".txt",".csv",".tsv"): return "code"
    return "other"

def _env_tag(rel: str) -> Optional[str]:
    s = rel.lower()
    for tag in ("dev","qa","staging","stage","prod","production","vbg","vcg","vbgalpha","sit","uat"):
        if f"/{tag}/" in s or f"-{tag}" in s or f"_{tag}." in s or s.endswith(f"-{tag}") or f"/{tag}-" in s:
            return "staging" if tag=="stage" else ("prod" if tag=="production" else tag)
    return None

# -------- Repo scan & structural diff --------
def _tree(root: Path) -> List[str]:
    out: List[str] = []
    for p in root.rglob("*"):
        if p.is_file():
            rel_path = str(p.relative_to(root)).replace("\\","/")
            # Skip .git directory and hidden files
            if not rel_path.startswith('.git/') and not rel_path.startswith('.'):
                out.append(rel_path)
    return sorted(out)

def _classify(root: Path, rels: List[str]) -> List[Dict[str, Any]]:
    out = []
    for rel in rels:
        p = root / rel
        st = p.stat()
        out.append({
            "path": rel,
            "name": p.name,
            "ext": p.suffix.lower(),
            "size": st.st_size,
            "mtime": st.st_mtime,
            "sha256": _sha256_file(p),
            "file_type": _file_type(p),
            "env_tag": _env_tag(rel),
        })
    return out

def _structural(g_files: List[Dict[str,Any]], c_files: List[Dict[str,Any]]) -> Dict[str, Any]:
    gmap = {f["path"]: f for f in g_files}; cmap = {f["path"]: f for f in c_files}
    added, removed, modified, renamed = [], [], [], []

    for p in cmap.keys() - gmap.keys(): added.append(p)
    for p in gmap.keys() - cmap.keys(): removed.append(p)
    for p in cmap.keys() & gmap.keys():
        if gmap[p]["sha256"] != cmap[p]["sha256"]:
            modified.append(p)

    # rename heuristic: same hash, different path
    gh, ch = {}, {}
    for f in g_files: gh.setdefault(f["sha256"], []).append(f["path"])
    for f in c_files: ch.setdefault(f["sha256"], []).append(f["path"])
    for h, g_paths in gh.items():
        for gp in g_paths:
            for cp in ch.get(h, []):
                if gp != cp and gp in removed and cp in added:
                    renamed.append({"from": gp, "to": cp})
                    removed.remove(gp); added.remove(cp)

    return {"added": sorted(added), "removed": sorted(removed), "modified": sorted(modified), "renamed": renamed}

# -------- Config parsing (for key-level diffs + line hints) --------
def _flatten(d: Dict[str, Any], prefix="") -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    # Handle case where d is not a dictionary (e.g., a plain string from YAML)
    if not isinstance(d, dict):
        if d is not None:
            out[prefix or "root"] = d
        return out
    
    for k, v in (d or {}).items():
        nk = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict): out.update(_flatten(v, nk))
        else: out[nk] = v
    return out

def _parse_props(txt: str) -> Dict[str, Any]:
    out = {}
    for ln in txt.splitlines():
        s = ln.strip()
        if not s or s.startswith("#"): continue
        if "=" in s:
            k, v = s.split("=", 1); out[k.strip()] = v.strip()
    return out

def _parse_yaml_json(txt: str, ext: str) -> Optional[Dict[str, Any]]:
    try:
        import json, yaml  # type: ignore
        if ext == ".json": return json.loads(txt)
        if _HAVE_RUAMEL:
            y = YAML(typ="rt"); return y.load(txt)
        return yaml.safe_load(txt)
    except Exception:
        return None

def _parse_xml(txt: str) -> Dict[str, Any]:
    try: root = ET.fromstring(txt)
    except Exception: return {}
    out = {}
    def walk(n, path=""):
        tag = n.tag.split("}")[-1]
        p = f"{path}.{tag}" if path else tag
        if (n.text or "").strip():
            out[p] = (n.text or "").strip()
        for k,v in n.attrib.items():
            out[f"{p}[@{k}]"] = v
        for ch in list(n):
            walk(ch, p)
    walk(root); return out

def _parse_toml(txt: str) -> Dict[str, Any]:
    if not _toml: return _parse_props(txt)
    try: return _toml.loads(txt)
    except Exception: return _parse_props(txt)

def _parse_config(p: Path) -> Optional[Dict[str, Any]]:
    txt = _load_text(p)
    if txt is None: return None
    ext = p.suffix.lower()
    if ext in (".yml",".yaml",".json"): return _parse_yaml_json(txt, ext) or {}
    if ext in (".properties",".ini",".cfg",".conf",".toml",".config"): return _parse_toml(txt) if ext==".toml" else _parse_props(txt)
    if ext == ".xml": return _parse_xml(txt)
    return None

def _key_locator(filename: str, key: str) -> Dict[str, Any]:
    ext = Path(filename).suffix.lower()
    if ext in (".yml",".yaml"): t="yamlpath"
    elif ext == ".json": t="jsonpath"
    else: t="keypath"
    return {"type": t, "value": f"{filename}.{key}" if key else filename}

def _first_line_for_key(file_path: Path, key_tail: str) -> Optional[int]:
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    key = key_tail.split(".")[-1]
    for i, ln in enumerate(text.splitlines()):
        s = ln.strip()
        if s.startswith("#"):  # skip yaml comments
            continue
        if key in ln:
            return i + 1
    return None

def _semantic_config_diff(g_root: Path, c_root: Path, changed_paths: List[str]) -> Dict[str, Dict[str, Any]]:
    added, removed, changed = {}, {}, {}
    for rel in changed_paths:
        pg, pc = g_root/rel, c_root/rel
        if pc.suffix.lower() not in (".yml",".yaml",".json",".properties",".toml",".ini",".cfg",".conf",".config",".xml"):
            continue
        go = _parse_config(pg) if pg.exists() else None
        co = _parse_config(pc) if pc.exists() else None
        gf, cf = _flatten(go or {}), _flatten(co or {})
        gk, ck = set(gf), set(cf)
        for k in sorted(ck - gk): added[f"{rel}.{k}"] = cf[k]
        for k in sorted(gk - ck): removed[f"{rel}.{k}"] = gf[k]
        for k in sorted(ck & gk):
            if gf[k] != cf[k]: changed[f"{rel}.{k}"] = {"from": gf[k], "to": cf[k]}
    return {"added": added, "removed": removed, "changed": changed}

# -------- Comment-only hunk filter --------
_COMMENT_RE = re.compile(r"""^\s*(//|#|--|/\*|\*|<!--|;)\s*|^\s*\*/\s*$|^\s*--\s*$""")
def _looks_comment_only(lines: List[str], ext: str) -> bool:
    total = 0; commenty = 0
    for ln in lines:
        s = ln.strip()
        if not s: continue
        total += 1
        if _COMMENT_RE.match(s): commenty += 1
        elif s.startswith("/*") and s.endswith("*/"): commenty += 1
        elif s.startswith("<!--") and s.endswith("-->"): commenty += 1
        elif ext in (".yml",".yaml",".properties",".cfg",".conf",".ini") and s.startswith("#"): commenty += 1
        elif ext in (".py",".sh",".rb") and s.startswith("#"): commenty += 1
        elif ext in (".sql",) and s.startswith("--"): commenty += 1
        elif ext in (".js",".ts",".java",".go",".cs",".groovy",".kts",".c",".cpp",".h",".hpp") and s.startswith("//"): commenty += 1
    return total > 0 and commenty == total

# -------- Git-ready patch builders --------
def _git_diff_no_index(a: Path, b: Path, rel: str) -> Optional[str]:
    """Produce a git-apply-ready patch (candidate->golden) using `git diff --no-index`.
       We rewrite paths to `a/<rel>` and `b/<rel>` so it applies at -p0 from candidate root."""
    try:
        proc = subprocess.run(
            ["git", "diff", "--no-index", "--binary", "-U3", "--", str(a), str(b)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False
        )
        if proc.returncode not in (0,1):  # 0 = no diff, 1 = diff found
            return None
        patch = proc.stdout
        patch = re.sub(r"^diff --git a/.* b/.*$", f"diff --git a/{rel} b/{rel}", patch, flags=re.M)
        patch = re.sub(r"^--- a/.*$", f"--- a/{rel}", patch, flags=re.M)
        patch = re.sub(r"^\+\+\+ b/.*$", f"+++ b/{rel}", patch, flags=re.M)
        return patch.strip() if patch.strip() else None
    except Exception:
        return None

def _difflib_gitlike_patch(a_text: List[str], b_text: List[str], rel: str) -> str:
    ud = list(difflib.unified_diff(a_text, b_text, fromfile=f"a/{rel}", tofile=f"b/{rel}", n=3, lineterm="\n"))
    body = "".join(ud)
    if not body.strip():
        return ""
    header = f"diff --git a/{rel} b/{rel}\n"
    return header + body

HUNK_RE = re.compile(r'^@@\s*-(\d+),?(\d*)\s+\+(\d+),?(\d*)\s*@@')

def _parse_git_patch_hunks(patch_text: str) -> List[Dict[str, Any]]:
    hunks = []
    lines = patch_text.splitlines()
    i = 0
    while i < len(lines):
        m = HUNK_RE.match(lines[i])
        if not m:
            i += 1
            continue
        old_start = int(m.group(1))
        old_lines = int(m.group(2) or "1")
        new_start = int(m.group(3))
        new_lines = int(m.group(4) or "1")
        header = lines[i]
        i += 1
        body_lines = []
        while i < len(lines) and not HUNK_RE.match(lines[i]) and not lines[i].startswith("diff --git "):
            body_lines.append(lines[i])
            i += 1
        hunks.append({
            "old_start": old_start, "old_lines": old_lines,
            "new_start": new_start, "new_lines": new_lines,
            "body": "\n".join(body_lines), "header": header
        })
    return hunks

def _hunks_for_file(g_path: Path, c_path: Path, rel: str, max_hunks: int = 400) -> Tuple[List[Dict[str, Any]], str]:
    patch = None
    if _have_git():
        patch = _git_diff_no_index(c_path, g_path, rel)
    if not patch:
        a = (_load_text(g_path) or "").splitlines()
        b = (_load_text(c_path) or "").splitlines()
        patch = _difflib_gitlike_patch(b, a, rel)

    hunks: List[Dict[str, Any]] = []
    used = 0
    if patch:
        for h in _parse_git_patch_hunks(patch):
            if used >= max_hunks: break
            snippet = f"{h['header']}\n{h['body']}"
            ext = g_path.suffix.lower() or c_path.suffix.lower()
            if _looks_comment_only([ln for ln in h["body"].splitlines() if ln and ln[0] in " +-"], ext):
                continue
            hunks.append({
                "id": f"hunk:{rel}:{h['old_start']}-{h['old_start']+h['old_lines']-1}->{h['new_start']}-{h['new_start']+h['new_lines']-1}",
                "category": "code_hunk",
                "file": rel,
                "locator": {
                    "type": "unidiff",
                    "value": f"{rel}#{h['old_start']}-{h['old_lines']}-{h['new_start']}-{h['new_lines']}",
                    "old_start": h["old_start"], "old_lines": h["old_lines"],
                    "new_start": h["new_start"], "new_lines": h["new_lines"],
                    "hunk_header": h["header"]
                },
                "old": "", "new": "", "snippet": snippet[:4000]
            })
            used += 1
    return hunks, (patch or "")

# -------- Dependencies (Maven/NPM/Pip) --------
def _maven_props_and_deps(pom_text: str) -> Tuple[Dict[str,str], Dict[str,str]]:
    properties: Dict[str,str] = {}
    pb = re.search(r"<properties>(.*?)</properties>", pom_text, re.S)
    if pb:
        for m in re.finditer(r"<([a-zA-Z0-9\.\-_]+)>(.*?)</\1>", pb.group(1), re.S):
            properties[m.group(1)] = m.group(2).strip()
    deps: Dict[str,str] = {}
    for g,a,v in re.findall(r"<dependency>\s*<groupId>(.*?)</groupId>\s*<artifactId>(.*?)</artifactId>\s*(?:<version>(.*?)</version>)?", pom_text, re.S):
        ver = (v or "").strip()
        if ver.startswith("${") and ver.endswith("}"): ver = properties.get(ver[2:-1], ver)
        deps[f"{g}:{a}"] = ver
    return properties, deps

def extract_dependencies(root: Path) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    pom = root / "pom.xml"
    if pom.exists():
        txt = pom.read_text(encoding="utf-8", errors="ignore")
        props, deps = _maven_props_and_deps(txt)
        out["maven"] = {"all": deps, "properties": props}
    pkg = root / "package.json"
    if pkg.exists():
        try:
            obj = json.loads(pkg.read_text(encoding="utf-8"))
            dd = {**(obj.get("dependencies") or {}), **(obj.get("devDependencies") or {})}
            out["npm"] = {"all": dd}
        except Exception:
            pass
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

def dependency_diff(g: Dict[str, Dict[str, Any]], c: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    diff: Dict[str, Any] = {}
    eco = set(g) | set(c)
    for e in eco:
        if e == "maven":
            ga = (g.get("maven") or {}).get("all", {}); ca = (c.get("maven") or {}).get("all", {})
            added = {k:v for k,v in ca.items() if k not in ga}
            removed= {k:v for k,v in ga.items() if k not in ca}
            changed= {k: {"from": ga[k], "to": ca[k]} for k in ga.keys() & ca.keys() if ga[k] != ca[k]}
            diff[e] = {"added": added, "removed": removed, "changed": changed}
            gp = (g.get("maven") or {}).get("properties", {}) or {}
            cp = (c.get("maven") or {}).get("properties", {}) or {}
            pa = {k:v for k,v in cp.items() if k not in gp}
            pr = {k:v for k,v in gp.items() if k not in cp}
            pc = {k: {"from": gp[k], "to": cp[k]} for k in gp.keys() & cp.keys() if gp[k] != cp[k]}
            diff["maven_properties"] = {"added": pa, "removed": pr, "changed": pc}
        else:
            ga = (g.get(e) or {}).get("all", {}); ca = (c.get(e) or {}).get("all", {})
            added = {k:v for k,v in ca.items() if k not in ga}
            removed= {k:v for k,v in ga.items() if k not in ca}
            changed= {k: {"from": ga[k], "to": ca[k]} for k in ga.keys() & ca.keys() if ga[k] != ca[k]}
            diff[e] = {"added": added, "removed": removed, "changed": changed}
    return diff

# -------- Detectors (Spring/Jenkins/Docker) --------
def detector_spring_profiles(g_root: Path, c_root: Path) -> List[Dict[str, Any]]:
    out = []
    def collect(root: Path) -> Dict[str, Dict[str, Any]]:
        m: Dict[str, Dict[str, Any]] = {}
        for patt in ("**/application*.yml","**/application*.yaml","**/application*.properties"):
            for p in root.rglob(patt):
                rel = str(p.relative_to(root)).replace("\\","/")
                m[rel] = _parse_config(p) or {}
        return m
    g = collect(g_root); c = collect(c_root)
    for rel in sorted(set(g)|set(c)):
        gf = _flatten(g.get(rel, {}) or {}); cf = _flatten(c.get(rel,{}) or {})
        gk, ck = set(gf), set(cf)
        for k in sorted(ck - gk): out.append({"id": f"spring+{rel}.{k}","category":"spring_profile","file": rel,"locator": _key_locator(rel,k),"old": None,"new": cf[k]})
        for k in sorted(gk - ck): out.append({"id": f"spring-{rel}.{k}","category":"spring_profile","file": rel,"locator": _key_locator(rel,k),"old": gf[k],"new": None})
        for k in sorted(ck & gk):
            if gf[k] != cf[k]:
                out.append({"id": f"spring~{rel}.{k}","category":"spring_profile","file": rel,"locator": _key_locator(rel,k),"old": gf[k],"new": cf[k]})
    # line hints
    for d in out:
        fname, tail = d["locator"]["value"].split(".",1) if "." in d["locator"]["value"] else (d["file"], "")
        ls = _first_line_for_key(c_root/fname, tail) or _first_line_for_key(g_root/fname, tail)
        if ls: d["locator"]["line_start"] = ls
    return out

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
    return {k:v for k,v in out.items() if v is not None}

def detector_jenkinsfiles(g_root: Path, c_root: Path) -> List[Dict[str, Any]]:
    out = []
    def find_all(root: Path) -> List[str]:
        hits = []
        for p in root.rglob("Jenkinsfile*"):
            if p.is_file(): hits.append(str(p.relative_to(root)).replace("\\","/"))
        return hits
    names = sorted(set(find_all(g_root)) | set(find_all(c_root)))
    for rel in names:
        g = _summarize_jenkinsfile(g_root/rel) if (g_root/rel).exists() else {}
        c = _summarize_jenkinsfile(c_root/rel) if (c_root/rel).exists() else {}
        for k in sorted(set(g)|set(c)):
            gv, cv = g.get(k), c.get(k)
            if gv != cv:
                loc = {"type":"keypath","value": f"{rel}.{k}"}
                ls = _first_line_for_key(c_root/rel, k.split(".")[-1])
                if ls: loc["line_start"] = ls
                out.append({"id": f"jenkins~{rel}.{k}","category":"jenkins","file": rel,"locator": loc,"old": gv,"new": cv})
    return out

def detector_dockerfiles(g_root: Path, c_root: Path) -> List[Dict[str, Any]]:
    out = []
    def collect(root: Path) -> Dict[str, List[str]]:
        m: Dict[str, List[str]] = {}
        for p in root.rglob("Dockerfile*"):
            if p.is_file():
                rel = str(p.relative_to(root)).replace("\\","/")
                bases = []
                for ln in (_load_text(p) or "").splitlines():
                    s = ln.strip()
                    if s.upper().startswith("FROM "):
                        bases.append(s.split(None, 1)[1])
                m[rel] = bases
        return m
    g = collect(g_root); c = collect(c_root)
    for rel in sorted(set(g)|set(c)):
        gb, cb = g.get(rel, []), c.get(rel, [])
        for i in range(max(len(gb), len(cb))):
            old = gb[i] if i < len(gb) else None
            new = cb[i] if i < len(cb) else None
            if old != new:
                out.append({"id": f"docker~{rel}#{i}","category":"container","file": rel,
                            "locator":{"type":"keypath","value": f"{rel}.FROM[{i}]"}, "old": old, "new": new})
    return out

# -------- Binary / Archive deltas --------
def binary_deltas(g_root: Path, c_root: Path, modified: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for rel in modified:
        gp, cp = g_root/rel, c_root/rel
        if not gp.exists() or not cp.exists(): continue
        if _is_text(cp): continue
        d_meta = {"id": f"bin~{rel}","category":"binary_meta","file": rel,"locator":{"type":"path","value": rel},
                  "old":{"size": gp.stat().st_size,"sha256": _sha256_file(gp)}, "new":{"size": cp.stat().st_size,"sha256": _sha256_file(cp)}}
        out.append(d_meta)
        if zipfile.is_zipfile(gp) and zipfile.is_zipfile(cp):
            def entries(p: Path) -> Dict[str, int]:
                with zipfile.ZipFile(p) as z: return {i.filename: i.file_size for i in z.infolist()}
            ge, ce = entries(gp), entries(cp)
            added = {k: ce[k] for k in ce.keys() - ge.keys()}
            removed= {k: ge[k] for k in ge.keys() - ce.keys()}
            changed= {k: {"from": ge[k], "to": ce[k]} for k in ge.keys() & ce.keys() if ge[k] != ce[k]}
            if added or removed or changed:
                out.append({"id": f"zip~{rel}","category":"archive_delta","file": rel,"locator":{"type":"path","value": rel},
                            "old":{"entries": len(ge)}, "new":{"entries": len(ce)}, "diff":{"added": added,"removed": removed,"changed": changed}})
            def manifest_map(p: Path) -> Dict[str,str]:
                try:
                    with zipfile.ZipFile(p) as z:
                        with z.open("META-INF/MANIFEST.MF") as mf:
                            m = {}
                            for line in mf.read().decode("utf-8","ignore").splitlines():
                                if ":" in line:
                                    k,v = line.split(":",1); m[k.strip()] = v.strip()
                            return m
                except Exception:
                    return {}
            gm, cm = manifest_map(gp), manifest_map(cp)
            for k in sorted(set(gm)|set(cm)):
                if gm.get(k) != cm.get(k):
                    out.append({"id": f"manifest~{rel}.{k}","category":"archive_manifest","file": rel,
                                "locator":{"type":"keypath","value": f"{rel}.MANIFEST.{k}"},"old": gm.get(k),"new": cm.get(k)})
        if tarfile.is_tarfile(gp) and tarfile.is_tarfile(cp):
            def members(p: Path) -> Dict[str,int]:
                with tarfile.open(p, "r:*") as t:
                    return {m.name: (m.size or 0) for m in t.getmembers() if m.isfile()}
            ge, ce = members(gp), members(cp)
            added = {k: ce[k] for k in ce.keys() - ge.keys()}
            removed= {k: ge[k] for k in ge.keys() - ce.keys()}
            changed= {k: {"from": ge[k], "to": ce[k]} for k in ge.keys() & ce.keys() if ge[k] != ce[k]}
            if added or removed or changed:
                out.append({"id": f"tar~{rel}","category":"archive_delta","file": rel,"locator":{"type":"path","value": rel},
                            "old":{"entries": len(ge)}, "new":{"entries": len(ce)}, "diff":{"added": added,"removed": removed,"changed": changed}})
    return out

# -------- Policy tagging --------
def _policy_load(p: Optional[Path]) -> Dict[str, Any]:
    if not p or not p.exists(): return {}
    try:
        import yaml
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}

def _risk_level_and_reason(d: Dict[str, Any]) -> Tuple[str, str]:
    """
    Return (risk_level, risk_reason) where risk_level ∈ {high, med, low}.
    """
    cat = d.get("category","")
    file = (d.get("file") or "").lower()
    loc = ((d.get("locator") or {}).get("value") or "").lower()

    # High: credentials/secrets, prod-scope security, pipeline creds, base image changes in prod
    if any(tok in loc for tok in ("password","secret","token","credentialsid","db.password","db.username","jdbc.url","posdb_")):
        return "high", "Sensitive credential or connection parameter changed."
    if cat in ("jenkins","container") and ("credentials" in loc or "from[" in loc):
        return "high", "Pipeline credential or container base image changed."
    if cat == "spring_profile" and ("prod" in file or ".production" in file):
        return "high", "Production profile configuration changed."

    # Medium: code behavior diffs, dependency/version bumps, non-prod configs that can impact behavior
    if cat in ("code_hunk","dependency","build_config","spring_profile","config"):
        return "med", "Behavioral or version/configuration change."

    # Low: file presence, binary/package metadata, archive member count changes
    if cat in ("file","table","binary_meta","archive_delta","archive_manifest","other"):
        return "low", "Non-behavioral or metadata/package change."

    return "low", "Default low risk."

# --- Back-compat shim so older callsites won’t crash ---
def _risk_hint(d: Dict[str, Any]) -> str:
    level, _ = _risk_level_and_reason(d)
    return level  # "high" | "med" | "low"

def _tag_with_policy(d: Dict[str, Any], policies: Dict[str, Any]) -> Dict[str, Any]:
    # Base risk
    level, reason = _risk_level_and_reason(d)
    d["risk_level"] = level
    d["risk_reason"] = reason

    # Policy tags
    tag, rule = "suspect", ""
    env_allow = set(str(x).lower() for x in (policies.get("env_allow_keys") or []))
    loc_val = (d.get("locator") or {}).get("value","").lower()

    if any(tok in loc_val for tok in env_allow):
        tag, rule = "allowed_variance", "env_allow_keys"

    for inv in (policies.get("invariants") or []):
        lc = str(inv.get("locator_contains","")).lower()
        if lc and lc in loc_val:
            forbid = set(inv.get("forbid_values", []))
            if d.get("new") in forbid:
                tag, rule = "invariant_breach", (inv.get("name") or "invariant")

    d["policy"] = {"tag": tag, "rule": rule}
    return d

# -------- Build deltas & bundle --------
def _build_config_deltas(conf: Dict[str, Any]) -> List[Dict[str, Any]]:
    global golden_root, candidate_root  # ✅ Fixed: Access global variables
    deltas = []
    for k, v in (conf.get("added") or {}).items():
        fn, tail = k.split(".",1) if "." in k else (k,"")
        loc = _key_locator(fn, tail)
        ls = None
        if tail: ls = _first_line_for_key(Path(candidate_root)/fn, tail) or _first_line_for_key(Path(golden_root)/fn, tail)
        if ls: loc["line_start"] = ls
        d = {"id": f"cfg+{k}","category":"config","file": fn,"locator": loc,"old": None,"new": v}
        d["risk_hint"] = _risk_hint(d); deltas.append(d)
    for k, v in (conf.get("removed") or {}).items():
        fn, tail = k.split(".",1) if "." in k else (k,"")
        loc = _key_locator(fn, tail)
        ls = None
        if tail: ls = _first_line_for_key(Path(candidate_root)/fn, tail) or _first_line_for_key(Path(golden_root)/fn, tail)
        if ls: loc["line_start"] = ls
        d = {"id": f"cfg-{k}","category":"config","file": fn,"locator": loc,"old": v,"new": None}
        d["risk_hint"] = _risk_hint(d); deltas.append(d)
    for k, ch in (conf.get("changed") or {}).items():
        fn, tail = k.split(".",1) if "." in k else (k,"")
        loc = _key_locator(fn, tail)
        ls = None
        if tail: ls = _first_line_for_key(Path(candidate_root)/fn, tail) or _first_line_for_key(Path(golden_root)/fn, tail)
        if ls: loc["line_start"] = ls
        d = {"id": f"cfg~{k}","category":"config","file": fn,"locator": loc,"old": ch.get("from"),"new": ch.get("to")}
        d["risk_hint"] = _risk_hint(d); deltas.append(d)
    return deltas

def _build_dep_deltas(dd: Dict[str, Any]) -> List[Dict[str, Any]]:
    deltas = []
    for eco, blk in (dd or {}).items():
        if eco == "maven_properties":
            for k,v in (blk.get("added") or {}).items():
                d = {"id": f"mvnprop+{k}","category":"build_config","file":"pom.xml","locator":{"type":"keypath","value": f"pom.xml.properties.{k}"},"old": None,"new": v}
                d["risk_hint"] = _risk_hint(d); deltas.append(d)
            for k,v in (blk.get("removed") or {}).items():
                d = {"id": f"mvnprop-{k}","category":"build_config","file":"pom.xml","locator":{"type":"keypath","value": f"pom.xml.properties.{k}"},"old": v,"new": None}
                d["risk_hint"] = _risk_hint(d); deltas.append(d)
            for k,ch in (blk.get("changed") or {}).items():
                d = {"id": f"mvnprop~{k}","category":"build_config","file":"pom.xml","locator":{"type":"keypath","value": f"pom.xml.properties.{k}"},"old": ch.get("from"),"new": ch.get("to")}
                d["risk_hint"] = _risk_hint(d); deltas.append(d)
            continue
        for name, ver in (blk.get("added") or {}).items():
            d = {"id": f"dep+{eco}:{name}","category":"dependency","file": eco,"locator":{"type":"coord","value": f"{eco}:{name}"},"old": None,"new": ver}
            d["risk_hint"] = _risk_hint(d); deltas.append(d)
        for name, ver in (blk.get("removed") or {}).items():
            d = {"id": f"dep-{eco}:{name}","category":"dependency","file": eco,"locator":{"type":"coord","value": f"{eco}:{name}"},"old": ver,"new": None}
            d["risk_hint"] = _risk_hint(d); deltas.append(d)
        for name, ch in (blk.get("changed") or {}).items():
            d = {"id": f"dep~{eco}:{name}","category":"dependency","file": eco,"locator":{"type":"coord","value": f"{eco}:{name}"},"old": ch.get("from"),"new": ch.get("to")}
            d["risk_hint"] = _risk_hint(d); deltas.append(d)
    return deltas

def _build_file_presence_deltas(fc: Dict[str, Any]) -> List[Dict[str, Any]]:
    deltas = []
    for rel in fc.get("added", []):
        d={"id": f"file+{rel}","category":"file","file": rel,"locator":{"type":"path","value": rel},"old": None,"new": "present"}
        d["risk_hint"] = _risk_hint(d); deltas.append(d)
    for rel in fc.get("removed", []):
        d={"id": f"file-{rel}","category":"file","file": rel,"locator":{"type":"path","value": rel},"old":"present","new": None}
        d["risk_hint"] = _risk_hint(d); deltas.append(d)
    for rn in fc.get("renamed", []):
        oldp, newp = rn.get("from"), rn.get("to")
        d={"id": f"file~{oldp}->{newp}","category":"file","file": newp,"locator":{"type":"path","value": newp},"old": oldp,"new": newp}
        d["risk_hint"] = _risk_hint(d); deltas.append(d)
    return deltas

def _merge_deltas(deltas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge duplicate deltas from different detection mechanisms into single comprehensive deltas."""
    merged = {}
    code_hunks = {}
    
    # First pass: collect code hunks by file
    for delta in deltas:
        if delta.get("category") == "code_hunk":
            file = delta.get("file", "")
            if file not in code_hunks:
                code_hunks[file] = []
            code_hunks[file].append(delta)
    
    # Second pass: merge config deltas and match with code hunks
    for delta in deltas:
        if delta.get("category") == "code_hunk":
            continue  # Skip code hunks in this pass
            
        # Create a normalized key based on file and the actual config key
        file = delta.get("file", "")
        locator_value = delta.get("locator", {}).get("value", "")
        old_val = delta.get("old")
        new_val = delta.get("new")
        
        # Normalize file name (remove .yml extension for comparison)
        normalized_file = file.replace(".yml", "").replace(".yaml", "")
        
        # Extract the config key from different locator formats
        config_key = ""
        if "." in locator_value:
            parts = locator_value.split(".")
            if len(parts) > 1:
                # Remove filename part and get the actual config key
                config_key = ".".join(parts[1:])
        
        # Create merge key based on normalized file, config key, and values
        merge_key = f"{normalized_file}::{config_key}::{old_val}::{new_val}"
        
        if merge_key not in merged:
            # First occurrence - use it as base
            merged[merge_key] = delta.copy()
            merged[merge_key]["detection_sources"] = [delta.get("category", "unknown")]
        else:
            # Merge with existing delta
            existing = merged[merge_key]
            existing["detection_sources"].append(delta.get("category", "unknown"))
            
            # Prefer spring_profile category for Spring files, config for others
            if delta.get("category") == "spring_profile":
                existing["category"] = "spring_profile"
                existing["locator"] = delta["locator"]
                existing["id"] = delta["id"]
                existing["file"] = delta["file"]  # Use the spring detector's file name
            elif delta.get("category") == "config" and existing.get("category") not in ["spring_profile"]:
                existing["category"] = "config"
                existing["locator"] = delta["locator"]
                existing["id"] = delta["id"]
    
    # Third pass: Add code hunk information to matching config deltas
    for merge_key, merged_delta in merged.items():
        file = merged_delta.get("file", "")
        config_key = merge_key.split("::")[1]  # Extract config key from merge key
        
        # Look for matching code hunks
        if file in code_hunks:
            for hunk in code_hunks[file]:
                # Check if this hunk contains the config key
                snippet = hunk.get("snippet", "")
                if config_key and any(part in snippet for part in config_key.split(".")):
                    # Add code hunk information to the merged delta
                    merged_delta["detection_sources"].append("code_hunk")
                    merged_delta["code_snippet"] = snippet
                    merged_delta["hunk_info"] = {
                        "old_start": hunk.get("locator", {}).get("old_start"),
                        "old_lines": hunk.get("locator", {}).get("old_lines"),
                        "new_start": hunk.get("locator", {}).get("new_start"),
                        "new_lines": hunk.get("locator", {}).get("new_lines"),
                        "hunk_header": hunk.get("locator", {}).get("hunk_header")
                    }
                    break
    
    # Add any unmatched code hunks as separate deltas
    for file, hunks in code_hunks.items():
        for hunk in hunks:
            # Check if this hunk was already merged
            hunk_merged = False
            for merged_delta in merged.values():
                if "code_snippet" in merged_delta and merged_delta["code_snippet"] == hunk.get("snippet"):
                    hunk_merged = True
                    break
            
            if not hunk_merged:
                # Add as separate delta
                hunk_key = f"unmatched_hunk_{file}_{hunk.get('id', '')}"
                merged[hunk_key] = hunk.copy()
                merged[hunk_key]["detection_sources"] = ["code_hunk"]
    
    return list(merged.values())

def emit_bundle(out_dir: Path,
                golden: Path,
                candidate: Path,
                overview: Dict[str, Any],
                dep_diff: Dict[str, Any],
                conf_diff: Dict[str, Any],
                file_changes: Dict[str, Any],
                extra_deltas: List[Dict[str, Any]],
                per_file_patches: Dict[str, str],
                policies_path: Optional[Path]) -> Dict[str, Any]:
    # ✅ Fixed: Initialize global variables needed by helper functions
    global golden_root, candidate_root
    golden_root = golden
    candidate_root = candidate
    
    policies = _policy_load(policies_path)
    all_deltas = _build_config_deltas(conf_diff) + _build_dep_deltas(dep_diff) + _build_file_presence_deltas(file_changes) + extra_deltas
    
    # Merge duplicate deltas
    merged_deltas = _merge_deltas(all_deltas)
    tagged = [_tag_with_policy(d, policies) for d in merged_deltas]

    # ---- enrich overview/meta for UI header ----
    drifted_files_count = len(file_changes.get("added", [])) + len(file_changes.get("removed", [])) + len(file_changes.get("modified", []))

    meta = {
        "golden": str(golden),
        "candidate": str(candidate),
        "golden_name": golden.name,
        "candidate_name": candidate.name,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }

    # overview already contains total_files (calculated by config_collector_agent.py)
    overview_enriched = {
        **overview,
        "drifted_files": drifted_files_count,
        "added_files": len(file_changes.get("added", [])),
        "removed_files": len(file_changes.get("removed", [])),
        "modified_files": len(file_changes.get("modified", [])),
    }

    bundle = {
        "meta": meta,
        "overview": overview_enriched,
        "file_changes": file_changes,
        "dependencies": dep_diff,
        "configs": {"diff": conf_diff, "environment_keys": [], "possible_secrets": []},
        "deltas": tagged,
        "git_patches": per_file_patches
    }
    (out_dir/"context_bundle.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    return bundle

# -------- Main --------
# Default paths for arguments
DEFAULT_GOLDEN = "C:\\Users\\saja9l7\\Downloads\\gcp\\git_branches_small\\golden"
DEFAULT_CANDIDATE = "C:\\Users\\saja9l7\\Downloads\\gcp\\git_branches_small\\drifted"
DEFAULT_OUT = "C:\\Users\\saja9l7\\Downloads\\gcp\\git_branches_small\\llmcontext"
DEFAULT_POLICIES = "C:\\Users\\saja9l7\\Downloads\\gcp\\context_generator\\policies.yaml"

# Ensure arguments are explicitly optional
def parse_args():
    parser = argparse.ArgumentParser(description="Drift detection script")
    parser.add_argument("--golden", default=DEFAULT_GOLDEN, required=False, help="Path to the golden configuration (optional)")
    parser.add_argument("--candidate", default=DEFAULT_CANDIDATE, required=False, help="Path to the candidate configuration (optional)")
    parser.add_argument("--out", default=DEFAULT_OUT, required=False, help="Output directory for results (optional)")
    parser.add_argument("--policies", default=DEFAULT_POLICIES, required=False, help="Path to the policies file (optional)")
    return parser.parse_args()

def main():
    args = parse_args()

    global golden_root, candidate_root, g_files, c_files
    golden_root = Path(args.golden).resolve()
    candidate_root = Path(args.candidate).resolve()
    out_dir = Path(args.out).resolve(); out_dir.mkdir(parents=True, exist_ok=True)

    g_paths = _tree(golden_root); c_paths = _tree(candidate_root)
    g_files = _classify(golden_root, g_paths); c_files = _classify(candidate_root, c_paths)

    overview = {
        "golden_repo_name": golden_root.name,
        "candidate_repo_name": candidate_root.name,
        "golden_repo_path": str(golden_root),
        "candidate_repo_path": str(candidate_root),
        "golden_files": len(g_files),
        "candidate_files": len(c_files),
        "ci_present": any("jenkinsfile" in f["name"].lower() for f in c_files),
        "build_tools": [f["name"] for f in c_files if f["file_type"]=="build"][:10]
    }
    (out_dir/"repo_overview.json").write_text(json.dumps(overview, indent=2), encoding="utf-8")

    file_changes = _structural(g_files, c_files)
    (out_dir/"file_changes.json").write_text(json.dumps(file_changes, indent=2), encoding="utf-8")

    g_deps = extract_dependencies(golden_root); c_deps = extract_dependencies(candidate_root)
    dep_diff = dependency_diff(g_deps, c_deps)
    (out_dir/"dependency_diff.json").write_text(json.dumps(dep_diff, indent=2), encoding="utf-8")

    changed_paths = sorted(set(file_changes["modified"]) | set(file_changes["added"]))
    conf_diff = _semantic_config_diff(golden_root, candidate_root, changed_paths)
    (out_dir/"config_diff.json").write_text(json.dumps(conf_diff, indent=2), encoding="utf-8")

    # Detectors
    spring = detector_spring_profiles(golden_root, candidate_root)
    jenkins = detector_jenkinsfiles(golden_root, candidate_root)
    docker = detector_dockerfiles(golden_root, candidate_root)

    # Code hunks + per-file git-ready patches (EVERY modified text file)
    code_hunks: List[Dict[str, Any]] = []
    per_file_patch: Dict[str, str] = {}
    for rel in file_changes.get("modified", []):
        gp, cp = golden_root/rel, candidate_root/rel
        if not gp.exists() or not cp.exists(): continue
        if not _is_text(cp): continue
        hunks, patch = _hunks_for_file(gp, cp, rel)
        code_hunks.extend(hunks)
        if patch: per_file_patch[rel] = patch

    # Binary/archives
    bin_d = binary_deltas(golden_root, candidate_root, file_changes.get("modified", []))

    # Emit bundle
    extra = spring + jenkins + docker + code_hunks + bin_d
    policies_path = Path(args.policies).resolve() if args.policies else None
    bundle = emit_bundle(out_dir, golden_root, candidate_root, overview, dep_diff, conf_diff, file_changes, extra, per_file_patch, policies_path)

    # For convenience, also write individual file patches to disk
    patches_dir = out_dir / "patches"
    patches_dir.mkdir(exist_ok=True)
    for rel, patch in per_file_patch.items():
        safe = rel.replace("/", "__")
        (patches_dir / f"{safe}.patch").write_text(patch, encoding="utf-8")

    # Top-level summary for quick CLI checks
    fc = file_changes
    print(json.dumps({
        "out_dir": str(out_dir),
        "meta": bundle.get("meta", {}),
        "stats": {
            "total_files": bundle["overview"]["total_files"],
            "drifted_files": bundle["overview"]["drifted_files"],
            "added": len(fc.get("added", [])),
            "removed": len(fc.get("removed", [])),
            "modified": len(fc.get("modified", [])),
        },
        "artifacts": [p.name for p in out_dir.iterdir() if p.is_file()],
        "patches": [p.name for p in (out_dir / "patches").iterdir()]
    }, indent=2))

if __name__ == "__main__":
    main()