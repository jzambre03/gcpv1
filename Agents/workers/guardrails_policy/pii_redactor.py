"""
PII Redactor - Detect and Redact Sensitive Information

Detects personally identifiable information (PII) and credentials,
then redacts them before further processing.
"""

import re
import logging
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger(__name__)


class PIIRedactor:
    """
    Detects and redacts PII, credentials, and secrets from configuration deltas.
    """
    
    # PII Patterns
    PII_PATTERNS = {
        # Personal Information
        'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'phone_us': r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
        'phone_intl': r'\+\d{1,3}[-.]?\d{1,14}\b',
        'ssn': r'\b\d{3}-\d{2}-\d{4}\b',
        
        # Financial
        'credit_card': r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
        'iban': r'\b[A-Z]{2}\d{2}[A-Z0-9]{1,30}\b',
        
        # Credentials & Secrets
        'api_key': r'(?i)(api[_-]?key|apikey)\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?',
        'password': r'(?i)(password|passwd|pwd)\s*[:=]\s*["\']?([^\s"\']+)["\']?',
        'jwt_token': r'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}',
        'private_key': r'-----BEGIN (RSA |EC )?PRIVATE KEY-----',
        
        # Cloud Provider Keys
        'aws_access_key': r'(A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}',
        'aws_secret': r'(?i)aws[_-]?secret[_-]?access[_-]?key["\']?\s*[:=]\s*["\']?([a-zA-Z0-9/+=]{40})["\']?',
        'gcp_key': r'(?i)AIza[0-9A-Za-z\-_]{35}',
        'azure_key': r'(?i)[a-zA-Z0-9]{52}==',
        
        # GitLab/GitHub
        'gitlab_token': r'glpat-[a-zA-Z0-9\-_]{20,}',
        'github_token': r'gh[pousr]_[A-Za-z0-9_]{36,}',
    }
    
    def __init__(self):
        """Initialize PII Redactor with compiled regex patterns"""
        self.compiled_patterns = {
            pii_type: re.compile(pattern, re.IGNORECASE | re.MULTILINE)
            for pii_type, pattern in self.PII_PATTERNS.items()
        }
    
    def scan_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Scan text for PII patterns.
        
        Args:
            text: Text to scan
            
        Returns:
            List of PII findings with type and location
        """
        findings = []
        
        if not text or not isinstance(text, str):
            return findings
        
        for pii_type, pattern in self.compiled_patterns.items():
            matches = pattern.finditer(text)
            for match in matches:
                findings.append({
                    'type': pii_type,
                    'value': match.group(0),
                    'start': match.start(),
                    'end': match.end()
                })
        
        return findings
    
    def redact_text(self, text: str) -> Tuple[str, List[str]]:
        """
        Redact PII from text.
        
        Args:
            text: Text to redact
            
        Returns:
            Tuple of (redacted_text, pii_types_found)
        """
        if not text or not isinstance(text, str):
            return text, []
        
        redacted = text
        pii_types_found = []
        
        for pii_type, pattern in self.compiled_patterns.items():
            matches = list(pattern.finditer(text))
            if matches:
                pii_types_found.append(pii_type)
                # Replace from end to start to preserve positions
                for match in reversed(matches):
                    redacted = (
                        redacted[:match.start()] +
                        f'[REDACTED_{pii_type.upper()}]' +
                        redacted[match.end():]
                    )
        
        return redacted, list(set(pii_types_found))
    
    def redact_delta(self, delta: Dict[str, Any]) -> Dict[str, Any]:
        """
        Redact PII from a single delta.
        
        Args:
            delta: Delta dictionary with 'old' and 'new' values
            
        Returns:
            Redacted delta with PII metadata
        """
        redacted = delta.copy()
        pii_found = []
        
        # Check old and new values
        for field in ['old', 'new']:
            if field in redacted and isinstance(redacted[field], str):
                original = redacted[field]
                redacted_value, found_types = self.redact_text(original)
                redacted[field] = redacted_value
                pii_found.extend(found_types)
        
        # Add metadata about redaction
        if pii_found:
            redacted['pii_redacted'] = True
            redacted['pii_types'] = list(set(pii_found))
        else:
            redacted['pii_redacted'] = False
            redacted['pii_types'] = []
        
        return redacted
    
    def redact_context_bundle(self, context_bundle: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Redact PII from entire context bundle.
        
        Args:
            context_bundle: Full context bundle from Drift Detector
            
        Returns:
            Tuple of (redacted_bundle, pii_report)
        """
        redacted = context_bundle.copy()
        pii_report = {
            'instances_found': 0,
            'types': set(),
            'redacted': False
        }
        
        # Redact deltas
        if 'deltas' in redacted:
            redacted_deltas = []
            for delta in redacted['deltas']:
                redacted_delta = self.redact_delta(delta)
                redacted_deltas.append(redacted_delta)
                
                if redacted_delta.get('pii_redacted'):
                    pii_report['instances_found'] += 1
                    pii_report['types'].update(redacted_delta.get('pii_types', []))
            
            redacted['deltas'] = redacted_deltas
        
        # Update report
        pii_report['redacted'] = pii_report['instances_found'] > 0
        pii_report['types'] = list(pii_report['types'])
        
        # Add report to bundle
        redacted['pii_redaction_report'] = pii_report
        
        return redacted, pii_report

