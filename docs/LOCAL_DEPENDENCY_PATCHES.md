# Local dependency patches

## llama.cpp web UI dependency snapshot

The ignored `tools/llama.cpp` checkout contains the local commit
`1dd8f7e3152c4efefe163f52cb4dee6bc4b15ed8` (`chore: remediate webui snyk findings`).
This patch preserves that existing delta in Venom's published history without
requiring a new fork or modifying the upstream repository.

- Upstream base: `5f4cdac3857ec3915c069caf3dec4f35af1691a1`.
- Scope: `tools/server/webui/package.json` and `package-lock.json` inside llama.cpp.
- Patch: [llama-cpp-webui-dependencies.patch](patches/llama-cpp-webui-dependencies.patch).
- SHA-256: `f6e8d2994bf2f5dd2c0a893747fddb046ac9b14ae35a3f23cca96871126d90e8`.

The snapshot updates the MCP SDK and pins transitive web UI dependencies. It is
a historical local patch, not a current vulnerability audit or an automatic
update of the installed inference engine. It does not change the C++ model
runtime. The existing patched checkout remains in place.

For a clean checkout at the recorded base, validate before applying:

```bash
git -C tools/llama.cpp apply --check ../../docs/patches/llama-cpp-webui-dependencies.patch
git -C tools/llama.cpp apply ../../docs/patches/llama-cpp-webui-dependencies.patch
```

Do not apply it twice. A checkout already containing the patch can be checked
with `git apply --check --reverse` against the same file. Newer upstream versions
need a separate dependency review before reuse.

Validation: the patch applied to temporary copies of both base files; the
resulting bytes matched the local commit exactly. Reverse application was also
checked against the installed checkout. No dependency installation, runtime
restart or new security scan was performed for this archival change.
