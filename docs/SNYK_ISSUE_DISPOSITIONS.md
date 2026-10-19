# Snyk issue dispositions

## CVE-2023-45853 — backend Bookworm zlib1g (2026-10-19)

**Disposition: not affected for the reviewed Debian binary package.** This is not a code fix or acceptance of an exploitable vulnerability. It does not qualify other findings or profiles.

| Scope | Verified value |
| --- | --- |
| Snyk issue | `SNYK-DEBIAN12-ZLIB-6008963` |
| Source commit | `df8245c27f837d2afe250780b5d48283a2825488` |
| Base image | `python:3.14.8-slim-bookworm@sha256:48b13b003dda20b16f9442b8475aa05fe21bf6579a8c881db92ffb4d8fd20f83` |
| Reviewed final image ID | `sha256:175c3c339af00e4526d6f90d15598f492ac56175f801ebf0c78b26f8f1a906ce` |
| Package | `zlib1g:amd64` / `1:1.2.13.dfsg-1` |
| Review expiry | 2026-11-18 23:59:59 UTC; reassess earlier on base or dependency change |

### Evidence

The CVE concerns MiniZip. [Debian's tracker](https://security-tracker.debian.org/tracker/CVE-2023-45853) explains that Bookworm's zlib source does not build/distribute the affected contrib/minizip code. The [binary package file list](https://packages.debian.org/bookworm/amd64/zlib1g/filelist) contains libz and documentation.

The exact backend Dockerfile and tracked inputs built successfully; hash-locked installs and `pip check` passed. The final image inventory contains 121 OS packages and 98 Python distributions. No MiniZip package, filename or selected MiniZip markers were found in 647 inspected ELF files. Marker searches cannot exclude every stripped static implementation; the primary justification is the Debian binary-package assessment.

### Scanner outcome and policy scope

The raw final-image Snyk scan reports **1 Critical / 7 High / 2 Medium / 162 Low**. A separate opt-in policy for this issue and exact package version yields **0 Critical / 7 High / 2 Medium / 162 Low**: only this Snyk ID is removed. Other findings still cause exit code 1.

The policy is held with local evidence, not in the repository-wide `.snyk`; it must only be used for the reviewed image. No organization-wide ignore or web project status was changed. The existing SCM backend project shows an empty inventory, which is not a security pass. Python distributions were inventoried, but this container scan returned only an OS result; it is not a complete Python vulnerability qualification.

**Scope control:** a deliberately nonmatching package version retains the Critical and all 172 raw issue IDs.

Local evidence: `docs_dev/_reports/snyk-backlog-20261019/critical-zlib/`, including `IMPLEMENTATION.json`, raw/reviewed scans, the scoped policy, package inventory and ELF hashes. Keep the raw result when applying this disposition. Rebuild and reassess before applying it to another image.

[Polish version](PL/SNYK_ISSUE_DISPOSITIONS.md).
