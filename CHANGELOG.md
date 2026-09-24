# Changelog

## v0.5.1.1

### Fixed

- Fixed legacy knowledge-card and note imports when multiple videos reuse local IDs such as `kc-1` or `note-1`.
- Preserved knowledge-card relationships during legacy import by remapping them to the new database IDs.
- Made legacy structured-artifact imports resumable when an interruption occurs between persisting data and recording import progress.
- Allowed the managed local MySQL instance to move to a new loopback port when its previously recorded port is no longer available.
