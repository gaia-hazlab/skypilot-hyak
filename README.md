# Connecting SkyPilot to UW Hyak Tillicum

This repo has configuration and notes for setting up compute jobs on [UW Hyak HPC](https://hyak.uw.edu/docs/tillicum/architecture) with [SkyPilot](https://github.com/skypilot-org/skypilot).

1. Sign up for the Hyak email list for maintenance and other updates:
https://mailman22.u.washington.edu/mailman/listinfo/hyak-users

**Important: As of 05/2026 Slurm clusters cannot be automatically terminated (autostop) after idle time, but you can specify sbatch_options:time for an explicit hard shutdown limit **


## Quickstart

After going through setup you can simply run

```
# Run a specific command (e.g. nvidia-smi) on a GPU node
sky launch --infra slurm/tillicum --gpus H200:1 -- nvidia-smi

# Run more elaborate jobs (python scripts) with a yaml config file
sky launch --infra slurm/klone --gpus A40:1 templates/klone-a40.yaml

# Run the same job on AWS instead of Hyak!
sky launch --infra aws --gpus A40:1 templates/klone-a40.yaml
```

**Important:** on Slurm `sky launch` spins up a compute node for a specified amount of time and either you must manually turn it off or wait until that time expires at which point the node is shut down. In contrast, skypilot is able to automatically shut down cloud resources after a specified 'idle time'.

The skypilot [YAML config/spec](https://docs.skypilot.co/en/stable/reference/yaml-spec.html) defined both cluster resources and the job (e.g. software environment setup, mounting storage buckets, what commands or scripts to run).


## Hyak Setup

See [docs/klone.md](./docs/klone.md) or [docs/tillicum.md](./docs/tillicum.md) for tips on setting up your Hyak environment depending on which cluster you have access to. The filesystem is *not* shared between the two clusters, so make sure to set up your environment variables and software on the correct cluster.

## SkyPilot Setup

SkyPilot offers an interface to launching jobs on Slurm clusters like Hyak. This allows you to run the same code on your laptop and on the cluster without having to worry about the differences in environment or job submission. See the official SkyPilot Slurm docs for more details:

https://docs.skypilot.co/en/latest/reference/slurm/slurm-getting-started.html#slurm-getting-started

### SkyPilot slurm config

We create a slurm config file (`~/.slurm/config`) that skypilot knows how to use. NOTE: not all `~/.ssh/config` are supported here, in particular skypilot handles Control itself. To avoid ssh IP bans from too many retry attempts, be sure to set the following in your `~/.ssh/config`:

```
# eliminate all public key attempts since these HPCs require MFA login!
Host klone.hyak.uw.edu tillicum.hyak.uw.edu
    PubkeyAuthentication no
```

And this in your `~/.slurm/config`:

```
Host klone
    HostName klone.hyak.uw.edu
    User scottyh
    IdentitiesOnly yes

Host tillicum
    HostName tillicum.hyak.uw.edu
    User scottyh
    IdentitiesOnly yes
```

#### SkyPilot per-cluster configuration

Note this is optional. However, by default on skypilot does not set slurm --time limits, causing jobs to fail to schedule on Hyak due to regular maintenance reservations. So we set a global limit of 1 hr below, which can be overriden in individual job configs.

This is set in `~/.sky/config.yaml` and looks like this:

```yaml
# cluster_configs need to be in `~/.sky/config.yaml` not `project/.sky.yaml`
# $SCRATCH must be set on the login node to change workdir from default of $HOME
slurm:
  sbatch_options:
    time: "0:05:00"
  cluster_configs:
    klone:
      workdir: $SCRATCH/skypilot
    tillicum:
      workdir: $SCRATCH/skypilot
      pricing:
        accelerators:
          H200: 0.90     # $/accelerator/hr (all-in, includes cpu/memory)
```

### Pixi environment

We install a single-user skypilot setup with [pixi](https://pixi.prefix.dev/latest/installation/):

```bash
pixi shell
sky check slurm
```

You should see this:
```
🎉 Enabled infra 🎉
  Slurm [compute]
    Allowed clusters:
    ├── klone
    └── tillicum
```

### Check remote resources

NOTE: this shows all resources but depending on groups and allocations you might not have access to all of them. `hyakalloc` shows what you actually have access to, but this is a good way to see all the options available on the cluster.

`sky gpus list --infra slurm`

```bash
Slurm Cluster: klone
GPU     REQUESTABLE_QTY_PER_NODE  UTILIZATION
2080TI  1, 2, 4, 8                68 of 84 free
A100    1, 2, 4, 8                24 of 64 free
A40     1, 2, 4, 8                147 of 256 free
H200    1, 2, 4, 8                44 of 64 free
L40     1, 2, 4, 8                41 of 120 free
L40S    1, 2, 4, 8                103 of 200 free
P100    1, 2, 4                   6 of 8 free
RTX6K   1, 2, 4, 8                87 of 88 free

Slurm Cluster: tillicum
GPU   REQUESTABLE_QTY_PER_NODE  UTILIZATION
H200  1, 2, 4, 8                112 of 192 free
```

## Using SkyPilot

Pick a GPU type from the table above and launch a job that just prints out the GPU information:

### Test job

```bash
sky launch --gpus A40:1 -- nvidia-smi

# specify a specific cluster
sky launch --infra slurm/tillicum --gpus H200:1 -- nvidia-smi
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

**Provisioning* logs are stored on the client computer automatically by date, for example: `cat ~/sky_logs/sky-2026-05-21-14-59-45-098750/provision.log`

STDOUT and STDERR from the job itself can be streamed with `sky logs sky-9f4c-scotthenderson` while the cluster is running.

But after the fact you can ssh into the login node and find copies of the actual SBATCH script (e.g`$SCRATCH/skypilot/.sky_provision/sky-9f4c-scotthenderson-d7836230.sh`) that launches the *cluster* on a compute node.

And the actual job stdout/stderr is in `$SCRATCH/skypilot/.sky_clusters/` for example, since in the examples we just run 1 job we have: `.sky_clusters/sky-9b22-scotthenderson-d7836230/sky_logs/1--/run.log`

### Job submission with yaml config

```bash
# sky launch templates/tillicum-h200.yaml
sky launch templates/klone-a40.yaml
```

### Connect to VSCode Remote - SSH

Note the ssh command above (`ssh sky-9f4c-scotthenderson`) to connect to the head node of the cluster. You can use this to connect with VSCode Remote - SSH and do interactive development on the cluster!


### Common commands

```bash
# Check on jobs
sky status --refresh

# Launch UI dashboard
sky dashboard
```

### Launch on AWS instead of Hyak

In case Hyak is offline!

```
sky launch templates/aws-vscode.yaml --cluster vscode-aws-scott
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
