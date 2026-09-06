# Security Policy

Please report suspected vulnerabilities privately to **majdbayer77@gmail.com**.

Do not open public issues containing credentials, private keys, personal media/data, exploit payloads, or live infrastructure details before remediation.

Priority reports include unsafe file/path handling, command/process injection, arbitrary file access, malicious media/project input handling, credential leakage, and vulnerabilities in automation or external-tool integration boundaries.

Runtime credentials and machine-specific secrets must remain outside source control. Any credential that has ever entered Git history should be rotated/revoked at the provider.

Security fixes target the current default branch and maintained tool/package paths.
