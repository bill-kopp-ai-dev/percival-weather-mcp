# Security posture — `percival-weather-mcp`

This directory holds the product's own vulnerability disposition. It answers
the item that the F3 gate could not close for this server: the MCP had no
OpenVEX of its own, so the gateway's document was the only one — and it is
restricted to the gateway's image ID, not to this server's.

## Files

| File | What it is |
|---|---|
| `openvex.json` | OpenVEX document (schema 0.2.0) restricted to the audited image digest, with one statement per CVE triaged by the F3 gate. |
| `trivy-raw-f62d438-68087203.json` | Raw Trivy output for the 2026-10-31 local candidate scan. |
| `trivy-raw-c55e2347-f356343f.json` | Raw Trivy output for the CI candidate of commit `c55e2347`, image `sha256:f356343f…`. |
| `evidence-c55e2347-f356343f.json` | The manifest that describes that evidence set: source revision, image, scanner and the sha256 of every file. |

## Current state — 0.10.0

The image that is pinned for this product was built on 2026-11-06 by the
maintenance executor from commit
`48a14467126eb54cd552e6ba40fe0920246f0402` (clean tree):

| Field | Value |
|---|---|
| Version | 0.10.0 |
| Image ID | `sha256:e1b73fa5bb9b124e420ad03c77ab8ff23b698e9b7e8ab8849e2bc386f369921f` |
| Build context | `sha256:26adbf29d7d50a7247fc8d50b96abf29f6de92a88ab94c1151338ce252cfda1e` |
| Scan | **0 findings** at the LOW/MEDIUM/HIGH/CRITICAL gate |
| Published | No — no registry digest exists yet |

The executor scan is recorded as a receipt: the raw report is
`sha256:e41158e2c43607da08cb5fc2fc545323334f1b4088c5bcfdf269e9daa86c5c9a`,
the SBOM is
`sha256:0591828c5c878833215b73995a69ddf4a75440f100c0da8caa7801ae78dc0157`,
and the scanner is
`sha256:7689b4dacbf7f73c3182005654b07aa84c7f63e060201f09de748b31610c739f`.
The executor keeps those bytes on the host and exposes no operation that
returns them, so the receipt is the only form of that scan available here.

## The CI evidence set

The CI job (`.github/workflows/ci.yml`) builds the same source, scans it with
the same gate and now publishes the result to the `evidence/trivy` branch,
where it is readable without a token. The set for commit `c55e2347` is
archived in this directory and states its own subject:

| Field | Value |
|---|---|
| Source revision | `c55e23472c3012ee776e6d5f44a8433f6271a37c` |
| Image ID | `sha256:f356343fdd67146d6aef8555c76f5e518bbfa137294e5f4d3d01cae3b338a559` |
| Raw report | `sha256:e5d3d305324abcf1258749bb2cbf5a5f298455b15cfee60f7b663540bfcb75ef` (459048 bytes) |
| SBOM | `sha256:364df07eb3d2439638f8cb9236c7c6df09499fd2893fdac75f6ca4a71bb5469c` |
| Scanner | Trivy **0.70.0**, `--scanners vuln`, severities UNKNOWN/LOW/MEDIUM/HIGH/CRITICAL |
| Result | **0 vulnerabilities** — 0 in the Debian OS packages (104 packages), 0 in the Python packages (40 packages) |

The archived report covers the commit that produced it. Every later commit
produces a different image and a different report, because the build stamps
the layers with the commit timestamp, so this file always trails `main` by one
commit. The scan that closes a release is the one bound to the published
digest.

The raw file was renamed here to follow this directory's convention; its
bytes are unchanged and the manifest records their sha256.

## The scanner pin did not hold

This report was produced by Trivy 0.70.0, although the workflow claimed to pin
0.76.1. `aquasecurity/trivy-action@v0.36.0` reads the `version` input and
ignores the `TRIVY_VERSION` environment variable, so the scan ran with the
action's own default, `v0.70.0` — older than the scanner the local scan uses,
and older than the database the local scan used.

A zero-finding result from a stale scanner is weaker evidence than the same
result from the current one, so the pin is now set on the input the action
reads, and the evidence manifest records the version that actually produced
the report next to the version the workflow pins. The CI fails the job when
the two disagree, which is what would have caught this. The archived manifest
shows the disagreement it recorded: 0.70.0 observed against 0.76.1 expected.

## The two builders do not agree on the same commit

Built from `c55e2347`, the executor produced
`sha256:30fb6e706cdae348d1c359855832d4b986dd4bf1d7066801dd25a892810d3bc7`
and the CI produced
`sha256:f356343fdd67146d6aef8555c76f5e518bbfa137294e5f4d3d01cae3b338a559`.
Both report 0 findings, and each report is valid for its own image, but the
two images are not the same bytes and a report must never be read as covering
an image other than the one it names. The published image will be built by
the CI as well, so its evidence is the scan of the published digest.

## The superseded candidate contradicted its own label

The candidate `sha256:40fa10ff…` was built from commit `875fff9`, before the
licence was aligned to MIT. Its Dockerfile copies `LICENSE` and `README.md`
into the image, so that image shipped the Apache-2.0 licence text and a
README announcing version 0.9.0, while its own OCI label declared
`licenses=MIT` and `version=0.10.0`. Publishing that image would have
published a licence contradicting the label.

The image was rebuilt from the current source, which carries the MIT
licence and the rewritten README, and the server was re-pinned to it. The
superseded image stays authorized so the previous state remains a rollback
target.

Because this candidate reports zero findings, no OpenVEX is due for it. The
document in `openvex.json` stays bound to the older digest below and must not
be reused for this candidate or for any future published artifact.

## Scope of the document

The statements cover the CVEs that the F3 triage
(the closed F3 tracker in the local working records) recorded against the
image that was running at the time
(`sha256:e75fdd4abc8a…`, 0 Critical / 44 High). They do **not** restate the
whole history of the gate: they record, for the audited candidate, why those
CVEs do not apply.

Each statement is bound to one product identifier — the audited digest — so
the document never applies to an image that was not scanned.

## Audited candidate (OpenVEX scope)

| Field | Value |
|---|---|
| Image | `percival-weather-mcp:stage2-candidate` (local, not published) |
| Image ID | `sha256:821ea0f6761f7cd3d98f5737afc4753060a5eeb87e335aeaf2be23c50d007a58` |
| Source revision | `ed2caa8cfd225bc5861a6670544d32f386b2bf3c` |
| Base image | `debian:forky-slim@sha256:4cee6ff3ebc49e32d55a857e25164ef8e5f8fecff2a186c6393f7e8bd8c23b53` |
| Python runtime | `python:3.12-slim-trixie@sha256:2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe` |
| Scanner | Trivy 0.76.1, vulnerability database of 2026-10-28 |
| Result | **0 vulnerabilities** in every severity — 104 Debian packages and the Python package set |

The scan is reproducible:

```sh
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$HOME/.cache/trivy:/root/.cache/trivy" \
  -v "$PWD:/out" \
  aquasec/trivy:latest image --scanners vuln --format json \
  --output /out/trivy-raw.json percival-weather-mcp:stage2-candidate
```

The same scan runs in the product CI
(`.github/workflows/ci.yml`, step "Scan the candidate for vulnerabilities")
and fails the job on any finding.

## Facts the statements rest on

Each statement was checked against the image, not only against the scanner:

| Fact | How it was checked |
|---|---|
| The process runs as `app` (UID 999) | `id` inside the container |
| No capabilities | `CapEff=0000000000000000` in `/proc/self/status` |
| `/usr/bin/mount` has no setuid bit | `ls -la /usr/bin/mount` → `-rwxr-xr-x` |
| `/usr/bin/nsenter` is absent | `ls` → *No such file or directory* |
| `/usr/bin/infocmp` is absent | `ls` → *No such file or directory* |
| `systemd-homed` is not installed | `dpkg-query -W systemd-homed` → *no packages found* |
| `Archive::Tar` is not importable | `python -c "import Archive.Tar"` → ModuleNotFoundError |
| `curl` is not installed | `command -v curl` → absent |

## Observations that are not statements

- The Debian base still ships setuid binaries (`su`, `passwd`, `chsh`,
  `chfn`, `gpasswd`). The Dockerfile only removes the setuid bit from
  `mount`. None of them provides the privileged mount/nsenter/fstab flow the
  util-linux advisories describe, and the deployed profile runs the rootfs
  read-only with `cap_drop: ALL`, but the owner should know they are there.
- The image is not published: the destination is the GitHub container
  registry of the project account,
  `ghcr.io/bill-kopp-ai-dev/percival-weather-mcp`, and no release exists
  there yet, so no `RepoDigest` exists. The `RepoDigest` of a published
  image will differ from the image IDs above, and the OpenVEX will have to
  be re-issued against the published digest — the statements themselves do
  not change, only the product identifier.

## Maintenance

The document is valid against the OpenVEX 0.2.0 JSON schema. Re-issue it
whenever the candidate digest changes: the statements are bound to a digest,
and a digest that was never scanned must not inherit a disposition.

## Later local candidate scan — 2026-10-31

The local image `percival-weather-mcp:0.9.0-f62d438` was scanned with Trivy
0.76.1 and vulnerability DB updated at 2026-10-31 13:09 UTC. The source label
is `f62d4383c89b63db7328bbbbb1a65846dff31531`; image ID is
`sha256:680872039a8f530f7feb53610478087c5271d5a5aec451c1f668f799e0e8a0ee`.
The scan found 0 vulnerabilities in Debian OS packages and Python packages;
raw output is `trivy-raw-f62d438-68087203.json`.

This scan is tied only to that local image ID. It does not update CI evidence,
create a published RepoDigest, verify the Registry namespace, or authorize
release. The existing OpenVEX statements remain bound to the earlier image and
must not be reused for this candidate or a later published artifact.
