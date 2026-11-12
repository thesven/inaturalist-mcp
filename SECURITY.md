# Security Policy

## Supported Versions

We provide security updates and patches for the current release stream:

| Version | Supported          |
| ------- | ------------------ |
| 0.2.x   | :white_check_mark: |
| < 0.2.0 | :x:                |

## Reporting a Vulnerability

We take the security of `inaturalist-mcp` seriously. If you believe you have discovered a security vulnerability, please do not open a public issue.

Instead, please report it responsibly by contacting:
- **Email**: `michael@mikesvendsen.net`
- **Subject**: `[SECURITY] inaturalist-mcp Vulnerability Report`

Please include:
- A clear description of the vulnerability and potential impact.
- Step-by-step instructions or proof-of-concept to reproduce the behavior.
- Any suggested mitigations.

You will receive an acknowledgment within 48 hours, followed by updates on the assessment and timeline for a patch.

## Security Practices

- **Zero Credential Leaks**: API tokens (if provided) are loaded via environment variables and never logged, exported to files, or included in client tool parameters.
- **Package Hygiene**: Build distributions are strictly checked to exclude `.env`, `.venv`, cache files, and private workspace paths.
- **Dependency Auditing**: Dependencies are pinned and audited using `uv.lock`.
