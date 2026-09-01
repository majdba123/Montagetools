# HEXA V31 validated release workflow

Every successful repository iteration follows this fixed sequence:

1. Implement the scoped fix.
2. Run targeted tests and the relevant complete suite.
3. Build a clean payload in a temporary staging directory.
4. Validate imports, CLI, resources, the V1.0 package contract, Premiere integration,
   and runtime selftest from that staging directory.
5. Replace `dist/latest` only after every staging check passes.
6. Report `READY TO INSTALL` with the current full Git SHA.

The user always installs by double-clicking the repository-root `bayer.bat`.
The launcher never falls back to repository source and invokes only
`dist/latest/INSTALL_HEXA_V31.bat`. ZIP files are archival artifacts only.
