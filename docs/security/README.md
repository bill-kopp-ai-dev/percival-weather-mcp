# Security posture — `percival-weather-mcp`

This directory holds the product's own vulnerability disposition. It answers
the item that the F3 gate could not close for this server: the MCP had no
OpenVEX of its own, so the gateway's document was the only one — and it is
restricted to the gateway's image ID, not to this server's.

## Files

| File | What it is |
|---|---|
| `openvex.json` | OpenVEX document (schema 0.2.0) restricted to the audited image digest, with one statement per CVE triaged by the F3 gate. |

## Scope of the document

The statements cover the CVEs that the F3 triage
([`docs/issues/2026-10-10-f3-status.md`](../issues/2026-10-10-f3-status.md))
recorded against the image that was running at the time
(`sha256:e75fdd4abc8a…`, 0 Critical / 44 High). They do **not** restate the
whole history of the gate: they record, for the current candidate, why those
CVEs do not apply.

Each statement is bound to one product identifier — the audited digest — so
the document never applies to an image that was not scanned.

## Audited candidate

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
- The image is not published: `docker manifest inspect mcp/percival-weather-mcp`
  answers `unauthorized`. The `RepoDigest` of a published image will differ
  from the image ID above, and the OpenVEX will have to be re-issued against
  the published digest — the statements themselves do not change, only the
  product identifier.

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
