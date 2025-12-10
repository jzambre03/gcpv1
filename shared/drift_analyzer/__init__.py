"""
Drift Analyzer Module
Provides precise configuration drift analysis with line-level locators.
Now using drift_v1.py for enhanced analysis capabilities.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
from .drift_v1 import (
    # Direct imports (same names)
    extract_dependencies,
    dependency_diff,
    detector_spring_profiles,
    detector_dockerfiles,
)

# Import with different names - need wrappers
from .drift_v1 import (
    _tree,
    _classify,
    _structural,
    _semantic_config_diff,
    detector_jenkinsfiles,
    binary_deltas,
    emit_bundle,
    _hunks_for_file,
)

# Compatibility wrappers for renamed functions
def extract_repo_tree(root: Path) -> List[str]:
    """Wrapper for _tree"""
    return _tree(root)

def classify_files(root: Path, relpaths: List[str]) -> List[Dict[str, Any]]:
    """Wrapper for _classify"""
    return _classify(root, relpaths)

def diff_structural(g_files: List[Dict[str, Any]], c_files: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Wrapper for _structural"""
    return _structural(g_files, c_files)

def semantic_config_diff(g_root: Path, c_root: Path, changed_paths: List[str]) -> Dict[str, Dict[str, Any]]:
    """Wrapper for _semantic_config_diff"""
    return _semantic_config_diff(g_root, c_root, changed_paths)

def detector_jenkinsfile(g_root: Path, c_root: Path) -> List[Dict[str, Any]]:
    """Wrapper for detector_jenkinsfiles (singular -> plural)"""
    return detector_jenkinsfiles(g_root, c_root)

def build_code_hunk_deltas(g_root: Path, c_root: Path, modified_paths: List[str]) -> List[Dict[str, Any]]:
    """Build code hunks for modified files"""
    deltas: List[Dict[str, Any]] = []
    for rel in modified_paths:
        gp, cp = g_root/rel, c_root/rel
        if not gp.exists() or not cp.exists():
            continue
        # Check if it's a text file using drift_v1's _is_text
        from .drift_v1 import _is_text
        if not _is_text(cp):
            continue
        hunks, _ = _hunks_for_file(gp, cp, rel)
        deltas.extend(hunks)
    return deltas

def build_binary_deltas(g_root: Path, c_root: Path, modified_paths: List[str]) -> List[Dict[str, Any]]:
    """Wrapper for binary_deltas"""
    return binary_deltas(g_root, c_root, modified_paths)

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
    """
    Wrapper for emit_bundle with compatibility for old signature.
    Note: drift_v1 uses per_file_patches instead of evidence parameter.
    The g_files bug has been fixed in drift_v1.py line 780.
    """
    # drift_v1.emit_bundle expects per_file_patches, but old code passes evidence
    # We'll generate empty patches dict for now
    per_file_patches: Dict[str, str] = {}
    
    # Call emit_bundle from drift_v1 (bug is now fixed)
    return emit_bundle(
        out_dir=out_dir,
        golden=golden,
        candidate=candidate,
        overview=overview,
        dep_diff=dep_diff,
        conf_diff=conf_diff,
        file_changes=file_changes,
        extra_deltas=extra_deltas or [],
        per_file_patches=per_file_patches,
        policies_path=policies_path
    )

__all__ = [
    # Core analysis functions
    'extract_repo_tree',
    'classify_files',
    'diff_structural',
    'semantic_config_diff',
    'extract_dependencies',
    'dependency_diff',
    
    # Specialized detectors
    'detector_spring_profiles',
    'detector_jenkinsfile',
    'detector_dockerfiles',
    'build_code_hunk_deltas',
    'build_binary_deltas',
    
    # Bundle generation
    'emit_context_bundle',
]
