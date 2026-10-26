# Local dependency patches

## llama.cpp web UI dependency snapshot

The ignored `tools/llama.cpp` checkout contains the local commit
`1dd8f7e3152c4efefe163f52cb4dee6bc4b15ed8` (`chore: remediate webui snyk findings`).
This patch captures that local delta with a reviewed compatibility correction:
Ajv 8 is scoped to the MCP SDK instead of being forced globally, so ESLint
retains its compatible Ajv 6 dependency. It requires no new fork or upstream change.

- Upstream base: `5f4cdac3857ec3915c069caf3dec4f35af1691a1`.
- Scope: `tools/server/webui/package.json` and `package-lock.json` inside llama.cpp.
- Patch: [llama-cpp-webui-dependencies.patch](patches/llama-cpp-webui-dependencies.patch).
- SHA-256: `ee8b4deefe213a98053ebbc908ea5c545a21cd2d1b1462898bfa9c9333e1376a`.

The snapshot updates the MCP SDK and pins transitive web UI dependencies. It is
a historical local patch, not a current vulnerability audit or an automatic
update of the installed inference engine. It does not change the C++ model
runtime. The existing checkout remains unchanged; this corrected recipe is not applied automatically.

For a clean checkout at the recorded base, validate before applying:

```bash
git -C tools/llama.cpp apply --check ../../docs/patches/llama-cpp-webui-dependencies.patch
git -C tools/llama.cpp apply ../../docs/patches/llama-cpp-webui-dependencies.patch
```

Do not apply it twice. A checkout already containing the patch can be checked
with `git apply --check --reverse` against the same file. The original local
commit predates the Ajv correction and is not byte-identical to this recipe. Newer upstream versions
need a separate dependency review before reuse.

Validation: the corrected patch applied to temporary copies of both base files
and reproduced the corrected manifests byte for byte; reverse application was
checked in that temporary tree. An isolated npm ci with install scripts disabled
resolved ESLint to Ajv 6.15.0 and the SDK to Ajv 8.18.0. A functional ESLint
configuration/schema check passed. The installed engine and checkout were not
modified, and this is not a new vulnerability scan.
