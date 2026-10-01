# Security

## Scope and limitations

SoonAI is distributed from a public GitHub repository. Anyone can download and copy its source; this project does not and cannot prevent source-code copying while the repository is public. Do not put credentials, private certificates, or signing keys in the repository.

The standalone Windows executable is not Authenticode-signed. Its SHA-256 value in `exesoonai/SHA256SUMS.txt` detects accidental or in-transit changes only when the checksum is obtained through a separately trusted channel. A checksum committed beside the executable does not protect against a compromised GitHub account or repository.

Datacenter tokens are encrypted at rest with AES-256-GCM, but the encryption key is stored in the same user profile. This helps avoid casual plaintext disclosure; it does not protect against malware or another process running as the same user, nor against an attacker who can read both files. Use a dedicated, least-privilege token and rotate it if the machine is compromised.

Automatic updates and installers download code from the project's GitHub repository over HTTPS. Review the source and release history before installing. Do not run an installer copied from an untrusted source.

## Reporting a vulnerability

Please report suspected vulnerabilities through GitHub's private vulnerability reporting for this repository when available. Include the affected version, reproduction steps, and impact. Do not include live API keys or credentials in the report; revoke and rotate any exposed secret immediately.
