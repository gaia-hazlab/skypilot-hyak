# Connecting SkyPilot to UW Hyak Tillicum

This repo has configuration and notes for setting up compute jobs on [UW Hyak HPC](https://hyak.uw.edu/docs/tillicum/architecture) with [SkyPilot](https://github.com/skypilot-org/skypilot).

1. Sign up for the Hyak email list for maintenance and other updates:
https://mailman22.u.washington.edu/mailman/listinfo/hyak-users

**Important: As of 05/2026 Slurm clusters cannot be automatically terminated (autostop) after idle time, but you can specify `sbatch_options.time` for an explicit hard shutdown limit.**


## Quickstart

*After going through setup* you can simply run:

```
# Run a specific command (e.g. nvidia-smi) on a GPU node
sky launch --infra slurm/tillicum --gpus H200:1 -- nvidia-smi

# Run more elaborate jobs (python scripts) with a yaml config file
sky launch templates/klone-a40.yaml

# Run a job on AWS instead of Hyak (must have local credentials)
AWS_PROFILE=gaia sky launch templates/aws-example.yaml
```

**Important:** on Slurm `sky launch` spins up a compute node for a specified amount of time and either you must manually turn it off or wait until that time expires at which point the node is shut down. In contrast, skypilot is able to automatically shut down cloud resources after a specified 'idle time'.

The skypilot [YAML config/spec](https://docs.skypilot.co/en/stable/reference/yaml-spec.html) defined both cluster resources and the job (e.g. software environment setup, mounting storage buckets, what commands or scripts to run).


## Hyak Setup

See [docs/klone.md](./docs/klone.md) or [docs/tillicum.md](./docs/tillicum.md) for notes and tips on setting up your Hyak environment depending on which cluster you have access to. The filesystem is *not* shared between the two clusters, so make sure to set up your environment variables and software on the correct cluster.

## SkyPilot Setup

SkyPilot offers an interface to launching jobs on Slurm clusters like Hyak. This allows you to run the same code on your laptop and on the cluster without having to worry about the differences in environment or job submission. See the official [SkyPilot Slurm docs](https://docs.skypilot.co/en/latest/reference/slurm/slurm-getting-started.html#slurm-getting-started) for more details.

### 0. Clone this repo

```bash
gh repo clone gaia-hazlab/skypilot-hyak
```


### 1. Pixi environment

We install a single-user SkyPilot setup with [pixi](https://pixi.prefix.dev/latest/installation/). All commands below are run from this repo, either inside `pixi shell` or prefixed with `pixi run`.

```bash
pixi shell
```

### 2. Hyak SSH and Slurm config

Run the setup script once with your UW NetID:

```bash
pixi run setup-hyak --uwnetid <uwnetid>
```

This creates two things, backing up any existing file before changing it:
- **`~/.slurm/config`**: adds `klone` and `tillicum` entries if they're missing (existing entries are left alone)
- **`~/.ssh/hyak.conf`**: `klone-login` / `tillicum-login` SSH aliases that share your Duo login with SkyPilot, plus an `Include ~/.ssh/hyak.conf` line at the top of `~/.ssh/config`. If you already defined `klone-login` / `tillicum-login` yourself in `~/.ssh/config`, the script warns you to delete those blocks. It is safe to rerun.

<details>
<summary><b>what the script does</b></summary>

### Why: Duo MFA and failed logins

Hyak requires Duo MFA on every new SSH login. SkyPilot polls the login node in the background (`squeue`, `sinfo`) and can't answer a Duo prompt, so unless it can reuse an already-authenticated connection, **every poll is a failed login, and enough failed logins get you blocked from Hyak.**

SkyPilot keeps its login-node connection at a fixed path that can't be configured, `/tmp/sky_ssh_<user_hash>/<md5('__default__')[:10]>/%C` (`<user_hash>` is unique per user, from `~/.sky/user_hash`). The generated `klone-login` / `tillicum-login` aliases use that same path, so one `ssh klone-login` is reused by SkyPilot for 24 hours. The generated config also stops SkyPilot from ever attempting a login itself: with no live connection, SkyPilot's SSH fails on your laptop instead of sending a failed login to Hyak.

#### `~/.slurm/config` vs `~/.ssh/config`

The two files use the same syntax but do different jobs:

- **`~/.slurm/config`** is read only by SkyPilot. Each `Host` entry defines a Slurm cluster, and its name is what you use in `--infra slurm/<name>` and `slurm.allowed_clusters` (here `klone` and `tillicum`). SkyPilot only reads `HostName`, `User`, `Port`, `IdentityFile`, `IdentitiesOnly`, `ProxyCommand` and `ProxyJump` from it; other SSH options (e.g. `ControlMaster`) are ignored.
- **`~/.ssh/config`** is read by the `ssh` program itself. SkyPilot runs `ssh` to the `HostName` above (e.g. `klone.hyak.uw.edu`), so the matching `Host klone.hyak.uw.edu` block in `~/.ssh/hyak.conf` applies to those connections, while your `klone-login` alias is used when you type `ssh klone-login`.

Don't add `ProxyJump klone-login` to `~/.slurm/config` to reuse your login: SkyPilot turns off its shared connection when a proxy is set, which makes every command a new login.

The generated `~/.slurm/config` looks like:

```
Host klone
    HostName klone.hyak.uw.edu
    User <uwnetid>
    IdentitiesOnly yes

Host tillicum
    HostName tillicum.hyak.uw.edu
    User <uwnetid>
    IdentitiesOnly yes
```

</details>

#### Daily workflow

```bash
ssh tillicum-login   # and/or: ssh klone-login -- Duo once, valid 24h (you can `exit` right away)
sky launch ...       # SkyPilot reuses that connection, no prompts
```

If a `sky` command fails with `Permission denied (...keyboard-interactive)`, the 24h connection expired (or you rebooted): run `ssh tillicum-login` / `ssh klone-login` again.

To keep background polling to a minimum:
- only list the clusters you are actively using in `slurm.allowed_clusters` (below)
- `sky down <cluster>` when done: a Slurm job hitting its time limit does *not* remove the cluster from `sky status`, and SkyPilot keeps polling clusters it thinks are UP
- `sky api stop` when you're finished for the day

### 3. SkyPilot config (`~/.sky/config.yaml`)

By default SkyPilot does not set a Slurm `--time` limit, which causes jobs to fail to schedule on Hyak around regular maintenance reservations. So we set a global default of 20 minutes below, which individual job YAMLs override with `config.slurm.sbatch_options.time`. Don't go much shorter: the limit includes SkyPilot installing its runtime on the node at the start of every launch, which has taken over 5 minutes on klone (the job is killed with `srun: error: Slurm job ... has expired` before your command runs). On klone, add `export UV_PYTHON_INSTALL_DIR=/tmp/uv-python-$USER` to `~/.bashrc` to avoid most of that; see [docs/remote-paths.md](docs/remote-paths.md). Per-cluster settings must go in `~/.sky/config.yaml`, not the project `.sky.yaml`:

```yaml
# SkyPilot copies local credentials for *every* cloud it knows about (AWS keys,
# gcloud, Azure tokens, ~/.kube/config) to each new cluster, including Hyak,
# even clouds not in allowed_clouds. NO_UPLOAD turns that off per cloud.
# (Drop the aws entry if your AWS VMs need your local AWS keys.)
aws:
  remote_identity: NO_UPLOAD
gcp:
  remote_identity: NO_UPLOAD
azure:
  remote_identity: NO_UPLOAD
kubernetes:
  remote_identity: NO_UPLOAD
ssh:
  remote_identity: NO_UPLOAD

slurm:
  # Only the clusters you're using right now: SkyPilot polls every allowed cluster
  allowed_clusters:
    - tillicum
    # - klone
  sbatch_options:
    time: "0:20:00"
  cluster_configs:
    # Keep SkyPilot's per-cluster runtime and state out of $HOME (10GB quota on klone).
    # $SCRATCH is expanded on the login node (set by default on klone and tillicum).
    klone:
      workdir: $SCRATCH/skypilot
    tillicum:
      workdir: $SCRATCH/skypilot
      pricing:
        accelerators:
          H200: 0.90     # $/accelerator/hr (all-in, includes cpu/memory)
```

After editing it, restart the SkyPilot API server: `sky api stop && sky api start`.

### 4. Check the connection

```bash
ssh tillicum-login   # MFA Login, if you haven't in the last 24h
sky check slurm
```

You should see your allowed clusters:
```
🎉 Enabled infra 🎉
  Slurm [compute]
    Allowed clusters:
    └── tillicum
```

### Check remote resources

NOTE: this shows all resources but depending on groups and allocations you might not have access to all of them. `hyakalloc` shows what you actually have access to, but this is a good way to see all the options available on the cluster. Only clusters in `slurm.allowed_clusters` are listed (the example below has both enabled).

`sky gpus list --infra slurm`

```bash
Slurm Cluster: klone
GPU     REQUESTABLE_QTY_PER_NODE  UTILIZATION
2080TI  1, 2, 4, 8                16 of 44 free
A100    1, 2, 4, 8                2 of 64 free
A40     1, 2, 4, 8                13 of 216 free
H200    1, 2, 4, 8                1 of 64 free
L40     1, 2, 4, 8                0 of 120 free
L40S    1, 2, 4, 8                18 of 200 free
P100    1, 2, 4                   0 of 8 free
RTX6K   1, 2, 4, 8                24 of 72 free
Slurm Cluster: tillicum
GPU   REQUESTABLE_QTY_PER_NODE  UTILIZATION
H200  1, 2, 4, 8, 16, 32, 56    55 of 240 free
```

## Using SkyPilot

Pick a GPU type from the table above and launch a job that just prints out the GPU information:

### Test jobs

```bash
# SkyPilot picks any allowed cluster with that GPU (A40 is klone only)
sky launch --infra slurm/klone --gpus A40:1 -- nvidia-smi

# specify a specific cluster
sky launch --infra slurm/tillicum --gpus H200:1 -- nvidia-smi

# CPU-only: leave out --gpus
sky launch --infra slurm/klone --cpus 1 --memory 4 -- nproc
```

You will be prompted to confirm executing the job, and then you should see output similar to this:

```
Command to run: nvidia-smi
Considered resources (1 node):
--------------------------------------------------------------------------------
 INFRA                 INSTANCE   vCPUs   Mem(GB)   GPUS    COST ($)   CHOSEN
--------------------------------------------------------------------------------
 Slurm (klone-login)   -          4       16        A40:1   0.00          ✔
--------------------------------------------------------------------------------
Launching a new cluster 'sky-9f4c-scotthenderson'. Proceed? [Y/n]: y
⚙︎ Launching on Slurm klone-login (ckpt).
└── Instance is up.
⠸ Preparing SkyPilot runtime (2/3 - dependencies)  View logs: sky logs --provision sky-9f
✓ Cluster launched: sky-9f4c-scotthenderson.  View logs: sky logs --provision sky-9f4c-scotthenderson
⚙︎ Syncing files.
⚙︎ Job submitted, ID: 1
├── Waiting for task resources on 1 node.
└── Job started. Streaming logs... (Ctrl-C to exit log streaming; job will not be killed)
(sky-cmd, pid=63073) bash: /mmfs1/home/scottyh/.sky_clusters/sky-9f4c-scotthenderson-d7836230/.bashrc: No such file or directory
(sky-cmd, pid=63073) Thu Apr 16 12:16:20 2026
(sky-cmd, pid=63073) +-----------------------------------------------------------------------------------------+
(sky-cmd, pid=63073) | NVIDIA-SMI 580.126.20             Driver Version: 580.126.20     CUDA Version: 13.0     |
(sky-cmd, pid=63073) +-----------------------------------------+------------------------+----------------------+
(sky-cmd, pid=63073) | GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
(sky-cmd, pid=63073) | Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
(sky-cmd, pid=63073) |                                         |                        |               MIG M. |
(sky-cmd, pid=63073) |=========================================+========================+======================|
(sky-cmd, pid=63073) |   0  NVIDIA A40                     Off |   00000000:C3:00.0 Off |                    0 |
(sky-cmd, pid=63073) |  0%   27C    P8             21W /  250W |       0MiB /  46068MiB |      0%      Default |
(sky-cmd, pid=63073) |                                         |                        |                  N/A |
(sky-cmd, pid=63073) +-----------------------------------------+------------------------+----------------------+
(sky-cmd, pid=63073)
(sky-cmd, pid=63073) +-----------------------------------------------------------------------------------------+
(sky-cmd, pid=63073) | Processes:                                                                              |
(sky-cmd, pid=63073) |  GPU   GI   CI              PID   Type   Process name                        GPU Memory |
(sky-cmd, pid=63073) |        ID   ID                                                               Usage      |
(sky-cmd, pid=63073) |=========================================================================================|
(sky-cmd, pid=63073) |  No running processes found                                                             |
(sky-cmd, pid=63073) +-----------------------------------------------------------------------------------------+
✓ Job finished (status: SUCCEEDED).

📋 Useful Commands
Job ID: 1
├── To cancel the job:          sky cancel sky-9f4c-scotthenderson 1
├── To stream job logs:         sky logs sky-9f4c-scotthenderson 1
└── To view job queue:          sky queue sky-9f4c-scotthenderson
Cluster name: sky-9f4c-scotthenderson
├── To log into the head VM:    ssh sky-9f4c-scotthenderson
├── To submit a job:            sky exec sky-9f4c-scotthenderson yaml_file
├── To stop the cluster:        sky stop sky-9f4c-scotthenderson
└── To teardown the cluster:    sky down sky-9f4c-scotthenderson
```

### Debugging

If a `sky` command fails with `Permission denied (...keyboard-interactive)`, your 24h Duo connection expired: run `ssh tillicum-login` / `ssh klone-login` again (see [Daily workflow](#daily-workflow)).

*Provisioning* logs are stored on the client computer automatically by date, for example: `cat ~/sky_logs/sky-2026-05-21-14-59-45-098750/provision.log`

STDOUT and STDERR from the job itself can be streamed with `sky logs sky-9f4c-scotthenderson` while the cluster is running.

But after the fact you can ssh into the login node and find copies of the actual SBATCH script (e.g`$SCRATCH/skypilot/.sky_provision/sky-9f4c-scotthenderson-d7836230.sh`) that launches the *cluster* on a compute node.

And the actual job stdout/stderr is in `$SCRATCH/skypilot/.sky_clusters/` for example, since in the examples we just run 1 job we have: `.sky_clusters/sky-9b22-scotthenderson-d7836230/sky_logs/1--/run.log`

### Job submission with yaml config

See [templates/](./templates/) for examples. The YAML `name:` is the *task* name; set the cluster name with `--cluster`:

```bash
sky launch templates/tillicum-h200.yaml
sky launch templates/klone-a40.yaml
sky launch templates/tillicum-cpu.yaml --cluster tillicum-cpu
```

CPU-only jobs: leave out `accelerators`. Tillicum has no CPU partition, so these run on spare cores of `gpu-h200` nodes. SkyPilot exports `OMP_NUM_THREADS=1` for every task, so add `export OMP_NUM_THREADS=$SLURM_JOB_CPUS_PER_NODE` at the top of `run:` (as in [templates/tillicum-cpu.yaml](./templates/tillicum-cpu.yaml)) or numpy/BLAS will only use one core.

### Connect to VSCode Remote - SSH

Note the ssh command above (`ssh sky-9f4c-scotthenderson`) to connect to the head node of the cluster. You can use this to connect with VSCode Remote - SSH and do interactive development on the cluster! This goes through the SkyPilot API server and your shared login connection, so it needs a live `ssh klone-login` / `ssh tillicum-login` too.


### Common commands

```bash
# Check on clusters
sky status --refresh
sky queue <cluster>          # jobs on a cluster
sky logs <cluster> [job-id]  # stream job output

# Done? Release the node and stop background polling
sky down <cluster>
sky api stop

# Launch UI dashboard
sky dashboard
```

### Launch on AWS instead of Hyak

In case Hyak is offline!

```
sky launch templates/aws-example.yaml --cluster vscode-aws-scott
```

Then conect with `ssh vscode-aws-scott` Or connect with VSCode Remote selecting the `vscode-aws-scott` Host.

Shut down with:
```
sky stop vscode-aws-scott
```

Restart with:
```
sky start vscode-aws-scott
code --remote ssh-remote+vscode-aws-scott /home/ubuntu/sky_workdir
```
