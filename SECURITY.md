# Security

Never put API tokens, Home Assistant backups, .storage data, logs with family data or production addresses into issues, pull requests or the repository. Use synthetic examples and redact personal data.

For a suspected vulnerability, use GitHub's private vulnerability reporting for this repository once enabled by the maintainer. Do not post credentials or an exploitable report publicly. No private reporting address is invented in this preparation. The maintainer must enable private reporting in repository security settings before inviting reports.

The current maintained version is 1.4.2. Unknown MCP tools remain subject to the existing explicit allowlist and action confirmation. The integration has no generic REST write tool. Run the local publication checks before committing. A clean automated scan is not proof that no secret exists; inspect the staged diff and any future Git history before publishing.
