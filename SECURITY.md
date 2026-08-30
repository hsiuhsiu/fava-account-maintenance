# Security and privacy

This extension is read-only, but its report operates on sensitive financial
metadata. A rendered report can contain account names, balances, dates,
counterpart accounts, and source locations even when a field is not currently
visible in the UI.

`source_mode` only controls source locations emitted by this extension. Fava's
standard page data may independently include ledger filenames.

Do not attach a real rendered page, screenshot, ledger, Fava cache, or server
log to a public issue. After this repository is published, use GitHub's private
security-advisory flow for vulnerabilities that could expose ledger data.
