# Bridge development

Follow README.md and docs/STATUS.md for current setup and limitations.

- Keep Node and Python files in sync; restart CC5 for Python changes. Runtime reload is disabled.
- Authenticate all HTTP requests. Default startup is read-only.
- Run offline tests before live work. Use saved disposable characters for live tests.
- After a timeout, query the operation ID; never blindly retry native mutations.
- Never use blanket Enter/Escape keystrokes to dismiss unknown dialogs.
- Preserve project checkpoints and distinguish native crashes from tool timeouts.
- Do not commit credentials, private references, CC5 assets or local reports.
