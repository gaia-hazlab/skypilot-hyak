# Remote Paths: where SkyPilot writes on Hyak

Why `sky launch` on klone can sit for 10+ minutes at `Preparing SkyPilot runtime (2/3 - dependencies)`, and how we work around it.

## TL;DR

- Downloading from GitHub is fast on both clusters (28 MiB in 0.6 s).
- Writing one large file is fast everywhere.
- **Creating many small files on klone's GPFS from a compute node is extremely slow.** SkyPilot's runtime setup has uv extract a managed CPython (4,872 files) into the per-cluster `HOME` on GPFS, so it can take 10+ minutes or hit the Slurm time limit.
- Fix: put uv's Python install on node-local `/tmp` with one line in your klone `~/.bashrc`:
  ```bash
  export UV_PYTHON_INSTALL_DIR=/tmp/uv-python-$USER
  ```

## Where things go

`workdir` and `tmpdir` come from `slurm.cluster_configs.<cluster>` in `~/.sky/config.yaml` (we set `workdir: $SCRATCH/skypilot`; `tmpdir` defaults to `/tmp`).

| What | Path on klone | Filesystem |
|---|---|---|
| sbatch scripts, `slurm-*.out` | `$SCRATCH/skypilot/.sky_provision/` | GPFS |
| Per-cluster `HOME` (`sky_workdir`, `sky_logs`, `~/.sky/wheels`, `~/.local/bin/uv`) | `$SCRATCH/skypilot/.sky_clusters/<cluster>-<user_hash>/` | GPFS |
| SkyPilot runtime venv (`skypilot-runtime`, ray, skylet, jobs db) | `/tmp/<cluster>-<user_hash>/` (`SKY_RUNTIME_DIR`) | node-local |
| uv download/wheel cache | `/tmp/uv_cache_<uid>` (hardcoded by SkyPilot, [#8245](https://github.com/skypilot-org/skypilot/pull/8245)) | node-local |
| uv-managed CPython 3.10 | default `$HOME/.local/share/uv/python`, i.e. the per-cluster `HOME` on GPFS (**the slow part**). With the `.bashrc` fix: `/tmp/uv-python-$USER` | node-local with fix |

Each new cluster gets a fresh `HOME`, so without the fix every launch re-extracts Python onto GPFS.

## Why the `.bashrc` fix reaches SkyPilot

SkyPilot runs every remote command as `/bin/bash --login -c '...'` over SSH on the login node, which sources your real `~/.bashrc`. It then calls `srun ... bash -c 'cd <cluster HOME> && export HOME=$PWD && <cmd>'`, and `srun` passes the login-node environment through to the compute node. So variables exported in `~/.bashrc` are visible to uv during runtime setup. Verified: a klone compute node shows `UV_PYTHON_INSTALL_DIR=/tmp/uv-python-scottyh`.

Notes:
- `UV_DATA_DIR` is **not** a uv variable (it came from an unmerged SkyPilot patch idea) and does nothing.
- `UV_CACHE_DIR` in `~/.bashrc` is overridden by SkyPilot's own `/tmp/uv_cache_<uid>` for its setup commands.
- `UV_PYTHON_INSTALL_DIR` also applies to your own `uv` use on login nodes. `/tmp` there is per login node, so uv may re-download Python when you land on a different one.
- `/tmp` is node-local and may be cleaned after jobs; uv just re-downloads Python (~2 s total).

## Measurements (2026-10-26)

From [scripts/check-download-speed.py](../scripts/check-download-speed.py): download the tarball uv uses, then extract its 4,872 files in each directory (stopping after 120 s).

**klone** (n3028, `ckpt`):

| Directory | Free | 1 large file | Files extracted | Files/s |
|---|---|---|---|---|
| `/tmp` | 348 GiB | 0.08 s | 4872/4872 in 1.3 s | 3874 |
| `/mmfs1/home/scottyh` | — | 0.19 s | 3973/4872 in 120 s | 33 |
| `/gscratch/scrubbed/scottyh` | 3.2 TiB of 150 TiB (98% full) | 1.13 s | 199/4872 in 120 s | 2 |

**tillicum** (g011, `gpu-h200`, debug QoS):

| Directory | Free | 1 large file | Files extracted | Files/s |
|---|---|---|---|---|
| `/tmp` | 3.5 TiB (NVMe) | 0.02 s | 4872/4872 in 0.8 s | 6192 |
| `/gpfs/home/scottyh` | — | 0.01 s | 4872/4872 in 1.9 s | 2546 |
| `/gpfs/scrubbed/scottyh` | 120 TiB | 0.01 s | 4872/4872 in 1.8 s | 2666 |

On klone the first file in `/gscratch/scrubbed` took 12.6 s to create, so this is metadata/file-creation latency, not bandwidth.

## Reproducing (for UWIT)

Copy [scripts/check-download-speed.py](../scripts/check-download-speed.py) to your home directory (standard library only, Python 3.6+) and run on a compute node:

```bash
# klone
srun -A escience -p ckpt -t 0:15:00 -c 1 --mem 4G -u python3 ~/check-download-speed.py
# tillicum
srun -A gaia -q debug -p gpu-h200 -t 0:15:00 -c 1 --mem 4G -u python3 ~/check-download-speed.py
```

It tests `/tmp`, `$HOME` and the scrubbed scratch dir by default (`--dirs` to override, `--max-seconds` to cap each directory) and ends with a summary table. Running it on a login node too would show whether the slowness is specific to compute nodes.

Check free space on a node's `/tmp`: `srun ... df -h /tmp`.

## Related upstream SkyPilot issues/PRs

- [#10509](https://github.com/skypilot-org/skypilot/pull/10509): set `UV_PYTHON_INSTALL_DIR` off networked storage (Kubernetes only, closed unmerged). Same root cause; the basis for asking for this on Slurm.
- [#8245](https://github.com/skypilot-org/skypilot/pull/8245): Slurm `UV_CACHE_DIR=/tmp/uv_cache_<uid>`.
- [#8382](https://github.com/skypilot-org/skypilot/pull/8382): `workdir` / `tmpdir` Slurm config.
- [#10562](https://github.com/skypilot-org/skypilot/pull/10562) (open): isolates runtime uv commands from uv config files, so don't rely on a `uv.toml` workaround.
- [#10781](https://github.com/skypilot-org/skypilot/pull/10781): timeouts and retries for stuck provisioning commands (after 0.14.1).
