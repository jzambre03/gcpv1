"""
Intent Guard - Detect Malicious Patterns

Detects suspicious patterns that might indicate malicious intent,
such as SQL injection, command injection, backdoors, etc.
"""

import re
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


class IntentGuard:
    """
    Detects malicious patterns in configuration changes.
    """
    
    # Suspicious Patterns
    SUSPICIOUS_PATTERNS = {
        'sql_injection': [
            r"';\s*DROP\s+TABLE",
            r"' OR '1'='1",
            r"UNION\s+SELECT",
            r"';?\s*DELETE\s+FROM",
            r"';?\s*UPDATE\s+.*SET",
        ],
        'command_injection': [
            r';\s*rm\s+-rf',
            r'&&\s*cat\s+/etc/passwd',
            r'\$\(.*\)',
            r'`.*`',
            r';\s*curl\s+http',
            r';\s*wget\s+http',
        ],
        'backdoor_ports': [
            r'port:\s*(4444|31337|1337|6666|6667)',
            r'PORT\s*=\s*(4444|31337|1337|6666|6667)',
        ],
        'debug_mode_prod': [
            r'debug:\s*true',
            r'DEBUG_MODE\s*=\s*true',
            r'debug\s*=\s*true',
        ],
        'wildcard_cors': [
            r'cors\.allowed-origins\s*[:=]\s*["\']?\*["\']?',
            r'CORS_ALLOWED_ORIGINS\s*=\s*["\']?\*["\']?',
        ],
        'disabled_security': [
            r'ssl\.enabled\s*[:=]\s*["\']?false["\']?',
            r'SSL_ENABLED\s*=\s*["\']?false["\']?',
            r'authentication\.enabled\s*[:=]\s*["\']?false["\']?',
        ],
    }
    
    def __init__(self):
        """Initialize Intent Guard with compiled regex patterns"""
        self.compiled_patterns = {}
        for category, patterns in self.SUSPICIOUS_PATTERNS.items():
            self.compiled_patterns[category] = [
                re.compile(pattern, re.IGNORECASE | re.MULTILINE)
                for pattern in patterns
            ]
    
    def scan_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Scan text for suspicious patterns.
        
        Args:
            text: Text to scan
            
        Returns:
            List of suspicious pattern findings
        """
        findings = []
        
        if not text or not isinstance(text, str):
            return findings
        
        for category, patterns in self.compiled_patterns.items():
            for pattern in patterns:
                matches = pattern.finditer(text)
                for match in matches:
                    findings.append({
                        'category': category,
                        'pattern': match.pattern,
                        'value': match.group(0),
                        'start': match.start(),
                        'end': match.end(),
                        'severity': self._get_severity(category)
                    })
        
        return findings
    
    def _get_severity(self, category: str) -> str:
        """Get severity level for pattern category"""
        severity_map = {
            'sql_injection': 'critical',
            'command_injection': 'critical',
            'backdoor_ports': 'high',
            'debug_mode_prod': 'high',
            'wildcard_cors': 'medium',
            'disabled_security': 'critical',
        }
        return severity_map.get(category, 'medium')
    
    def scan_delta(self, delta: Dict[str, Any]) -> Dict[str, Any]:
        """
        Scan a single delta for suspicious patterns.
        
        Args:
            delta: Delta dictionary with 'old' and 'new' values
            
        Returns:
            Delta with intent_guard metadata
        """
        scanned = delta.copy()
        findings = []
        
        # Check old and new values
        for field in ['old', 'new']:
            if field in scanned and isinstance(scanned[field], str):
                field_findings = self.scan_text(scanned[field])
                findings.extend(field_findings)
        
        # Add metadata
        if findings:
            scanned['intent_guard'] = {
                'suspicious': True,
                'patterns_detected': findings,
                'severity': max([f['severity'] for f in findings], default='low')
            }
        else:
            scanned['intent_guard'] = {
                'suspicious': False,
                'patterns_detected': [],
                'severity': 'none'
            }
        
        return scanned
    
    def scan_context_bundle(self, context_bundle: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Scan entire context bundle for suspicious patterns.
        
        Args:
            context_bundle: Full context bundle
            
        Returns:
            Tuple of (scanned_bundle, intent_report)
        """
        scanned = context_bundle.copy()
        intent_report = {
            'suspicious_patterns': [],
            'total_findings': 0,
            'critical_findings': 0,
            'safe': True
        }
        
        # Scan deltas
        if 'deltas' in scanned:
            scanned_deltas = []
            for delta in scanned['deltas']:
                scanned_delta = self.scan_delta(delta)
                scanned_deltas.append(scanned_delta)
                
                if scanned_delta.get('intent_guard', {}).get('suspicious'):
                    findings = scanned_delta['intent_guard']['patterns_detected']
                    intent_report['suspicious_patterns'].extend(findings)
                    intent_report['total_findings'] += len(findings)
                    
                    # Count critical findings
                    critical = [f for f in findings if f.get('severity') == 'critical']
                    intent_report['critical_findings'] += len(critical)
            
            scanned['deltas'] = scanned_deltas
        
        # Update report
        intent_report['safe'] = intent_report['total_findings'] == 0
        
        # Add report to bundle
        scanned['intent_guard_report'] = intent_report
        
        return scanned, intent_report

