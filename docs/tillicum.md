# Tillicum

Newer HPC GPU cluster with NVIDIA H200 GPUs. Best for large GPU jobs and training runs.

Usage Rate: $0.90/GPU Hour

Jobs are bound by a maximum of ~200GB system RAM and 8 CPUs per GPU.

Official Docs: https://hyak.uw.edu/docs/tillicum/architecture
Onboarding resources: https://github.com/UWrc/tillicum-onboarding

## SSH Config:

Set up your `~/.ssh/config` for easy access. The following will use a ssh key (`~/.ssh/id_ed25519`) for authentication so that you don't have to use your UW netid password every time (Only set this up if you're connecting from personal computer). It also caches Duo 2FA authentication for 24 hours so you won't have to do that every time either.

```
Host tillicum-login
    HostName tillicum.hyak.uw.edu
    User scottyh
    IdentityFile ~/.ssh/id_ed25519
    ForwardAgent yes
    ControlMaster auto
    ControlPath ~/.ssh/control-%r@%h:%p
    ControlPersist 24h
```

NOTE: if you don't have a key yet create one, the `-C` comment can be whatever you want, it's just a label for the key. Add a passphrase if you want more security, but I left it blank for ease of use.

```bash
ssh-keygen -t ed25519 -C "scottyh"
ssh-copy-id -i ~/.ssh/id_ed25519.pub tillicum-login
```

Now `ssh tillicum-login` should log you in without asking for a password, but will ask for Duo 2FA code (only once per 24 hours).


## Storage Setup

https://hyak.uw.edu/docs/tillicum/storage

The filesystem is *not* shared with Klone.

Note that the home directory (`/gpfs/home/UWNetID`) has a 10GB limit.

If you've joined a group with a storage allocation you can use that. It's convenient to set environment variables for these commonly used paths:

```bash
export PROJECT=/gpfs/projects/gaia/$USER
export SCRATCH=/gpfs/scrubbed/$USER
```


## User Environment Setup

Logging into klone for the first time you might want to set up environment variables or persistent software in your home directory. I use [pixi] to manage Python environments, so I install that in my home directory:

### Pixi

Since the home directory is limited to 10GB we tell pixi to install things in our more persistent project directory instead by setting environment variables:

```bash
export PIXI_HOME=$PROJECT/.pixi
export PIXI_CACHE_DIR=/tmp/cache/pixi

curl -fsSL https://pixi.sh/install.sh | sh
```


### .bashrc

To avoid having to set these variables every time you log in, add them to your `~/.bashrc`:

```bash
# User specific aliases and functions
export SCRATCH=/gpfs/scrubbed/$USER
export PROJECT=/gpfs/projects/gaia/$USER

export PIXI_HOME=$PROJECT/.pixi
export PIXI_CACHE_DIR=/tmp/cache/pixi

export PATH="$PIXI_HOME/bin:$PATH"
```

## Check available resources

### storage

`hyakstorage`
```bash
╭───────────────────────────────────────────────────────╮
│                       /gpfs/home                      │
├─────────────────────────┬─────────────────────┬───────┤
│          Quota          │         Disk        │       │
│   Type  │       ID      │ Usage │  Max  │  %  │ Files │
├─────────┼───────────────┼───────┼───────┼─────┼───────┤
│ User    │ scottyh       │ 1.48G │ 10.0G │ 15% │ 20.5k │
╰─────────┴───────────────┴───────┴───────┴─────┴───────╯
╭───────────────────────────────────────────────────────╮
│                     /gpfs/scrubbed                    │
├─────────────────────────┬─────────────────────┬───────┤
│          Quota          │         Disk        │       │
│   Type  │       ID      │ Usage │  Max  │  %  │ Files │
├─────────┼───────────────┼───────┼───────┼─────┼───────┤
│ User    │ scottyh       │    0K │  100T │  0% │     2 │
╰─────────┴───────────────┴───────┴───────┴─────┴───────╯
╭───────────────────────────────────────────────────────╮
│                /gpfs/projects/escience                │
├─────────────────────────┬─────────────────────┬───────┤
│          Quota          │         Disk        │       │
│   Type  │       ID      │ Usage │  Max  │  %  │ Files │
├─────────┼───────────────┼───────┼───────┼─────┼───────┤
│ Fileset │ -             │    0K │  100G │  0% │     1 │
╰─────────┴───────────────┴───────┴───────┴─────┴───────╯
╭───────────────────────────────────────────────────────╮
│                  /gpfs/projects/gaia                  │
├─────────────────────────┬─────────────────────┬───────┤
│          Quota          │         Disk        │       │
│   Type  │       ID      │ Usage │  Max  │  %  │ Files │
├─────────┼───────────────┼───────┼───────┼─────┼───────┤
│ Fileset │ -             │ 11.4G │ 1.00T │  1% │  145k │
│ User    │ scottyh       │ 11.4G │     - │  1% │  145k │
╰─────────┴───────────────┴───────┴───────┴─────┴───────╯
```


## Commands

```bash
# Fire up a compute node (automatically switches to node)
# NOTE: defauly 'quality of service' for 'interactive' is 8 hrs, you are charged by the hour
# NOTE: same directory structure
salloc --qos=interactive --gpus=1 --time=04:00:00

# Confirm you have GPU access on a compute node (NVIDIA H200)
nvidia-smi

# Check running nodes / jobs
squeue -u $USER

# Cancel a job
scancel JOB_ID
```
