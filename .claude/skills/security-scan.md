---
name: security-scan
tags: [domain, security]
appliesTo: [spawn]
---
# Security Scan

OWASP-based security review for application code.

## OWASP Top 10

- **Injection**: SQL, NoSQL, OS command, LDAP via unsanitized input
- **Broken Auth**: Weak session management, credential storage, token handling
- **Sensitive Data Exposure**: Unencrypted data, missing TLS, logged secrets
- **XXE**: XML external entity processing
- **Broken Access Control**: Missing authorization checks, privilege escalation
- **Security Misconfiguration**: Default credentials, verbose errors, open CORS
- **XSS**: Reflected, stored, and DOM-based cross-site scripting
- **Insecure Deserialization**: Untrusted data deserialization
- **Vulnerable Components**: Outdated dependencies with known CVEs
- **Insufficient Logging**: Missing audit trails for security events

## Auth/AuthZ Review

- Token storage and rotation practices
- AuthN vs AuthZ boundary correctness
- Permission checks near data access points
- Audit logging for sensitive actions

## Output: Critical / Warning / Info

Each finding: file:line, vulnerability type, impact, fix recommendation.
