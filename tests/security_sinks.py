"""The dangerous-sink pattern shared by test_security_owasp.py (scanning ClaimGuard's
own src/ and scripts/) and scripts/security_scan_clinicproj.py (scanning the adapted
clinicProj copy). Lives here, not in src/ or scripts/, on purpose: those two folders
are exactly what the scanner itself scans, and a copy of this pattern sitting in
either one would flag itself the moment it's written (the pattern's own text contains
the words it's looking for). tests/ is never scanned, so this is the one place the
word list can exist without matching itself.
"""
import re

# a bare call, not a method or a longer name: yara_x.compile() and validate_input() are fine
SINKS = re.compile(r'(?<![\w.])(eval|exec|compile|input|__import__)\s*\(|pickle|marshal|shelve|subprocess|os\.system|os\.popen'
                    r'|shell\s*=\s*True|yaml\.load\(')
