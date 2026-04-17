# Connecting SkyPilot to UW Hyak Tillicum

This repo has configuration and notes for setting up compute jobs on [UW Hyak HPC](https://hyak.uw.edu/docs/tillicum/architecture) with [SkyPilot](https://github.com/skypilot-org/skypilot).

1. Sign up for the Hyak email list for maintenance and other updates:
https://mailman22.u.washington.edu/mailman/listinfo/hyak-users

**Important: As of 04/2026 Slurm clusters cannot be automatically terminated (autostop) after idle time **

**Important: This issue needs to be resolved before using SkyPilot with Hyak: https://github.com/skypilot-org/skypilot/issues/9370 **


## Hyak Setup

See [docs/klone.md](./docs/klone.md) or [docs/tillicum.md](./docs/tillicum.md) for tips on setting up your Hyak environment depending on which cluster you have access to. The filesystem is *not* shared between the two clusters, so make sure to set up your environment variables and software on the correct cluster.

## SkyPilot Setup

SkyPilot offers an interface to launching jobs on Slurm clusters like Hyak. This allows you to run the same code on your laptop and on the cluster without having to worry about the differences in environment or job submission. See the official SkyPilot Slurm docs for more details:

https://docs.skypilot.co/en/latest/reference/slurm/slurm-getting-started.html#slurm-getting-started

### SkyPilot slurm config

We create a slurm config file (`~/.slurm/config`) that skypilot knows how to use. It mirrors what is in `~/.ssh/config`:

```
Host klone-login
    HostName klone.hyak.uw.edu
    User scottyh
    IdentityFile ~/.ssh/id_ed25519
    ForwardAgent yes
    ControlMaster auto
    ControlPath ~/.ssh/control-%r@%h:%p
    ControlPersist 24h

Host tillicum-login
    HostName tillicum.hyak.uw.edu
    User scottyh
    IdentityFile ~/.ssh/id_ed25519
    ForwardAgent yes
    ControlMaster auto
    ControlPath ~/.ssh/control-%r@%h:%p
    ControlPersist 24h
```

#### SkyPilot per-cluster configuration

This is set in `~/.sky/config.yaml` and looks like this:

```yaml
# cluster_configs need to be in `~/.sky/config.yaml` not `project/.sky.yaml`
# $SCRATCH must be set on the login node to change workdir from default of $HOME
slurm:
  # provision_timeout: 240
  cluster_configs:
    klone-login:
      workdir: $SCRATCH/skypilot
    tillicum-login:
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
    ├── klone-login
    └── tillicum-login
```

### Check remote resources

NOTE: this shows all resources but depending on groups and allocations you might not have access to all of them. `hyakalloc` shows what you actually have access to, but this is a good way to see all the options available on the cluster.

`sky gpus list --infra slurm`

```bash
Slurm Cluster: klone-login
GPU     REQUESTABLE_QTY_PER_NODE  UTILIZATION
2080TI  1, 2, 4, 8                70 of 84 free
A100    1, 2, 4, 8                40 of 64 free
A40     1, 2, 4, 8                143 of 256 free
H200    1, 2, 4, 8                62 of 64 free
L40     1, 2, 4, 8                37 of 120 free
L40S    1, 2, 4, 8                114 of 200 free
P100    1, 2, 4                   8 of 8 free
RTX6K   1, 2, 4, 8                51 of 88 free

Slurm Cluster: tillicum-login
GPU   REQUESTABLE_QTY_PER_NODE  UTILIZATION
H200  1, 2, 4, 8                67 of 192 free
```

## Using SkyPilot

Pick a GPU type from the table above and launch a job that just prints out the GPU information:

### Test job

```bash
sky launch --gpus A40:1 -- nvidia-smi
```

It will take several minutes to launch a compute node and run the job, but you should see output like this with different automatic names

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

### Debuggng

Skypilot creates slurm scripts on the login node and runds them. They are created in `/gscratch/scrubbed/scottyh/skypilot/.sky_provision/` and named by the cluster and jobid: `sky-d85d-scotthenderson-d7836230.sh` .

### Job submission with yaml config

```bash
sky launch templates/tillicum-H200.yaml
sky launch templates/klone-A40.yaml
```

### Connect to VSCode Remote - SSH

Note the ssh command above (`ssh sky-9f4c-scotthenderson`) to connect to the head node of the cluster. You can use this to connect with VSCode Remote - SSH and do interactive development on the cluster!


### Common commands

```bash
# Check on jobs
sky status

# Launch UI dashboard
sky dashboard
```
