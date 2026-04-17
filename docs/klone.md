# Klone

Older HPC cluster. Still has some GPU nodes but not as many as Tillicum. Best for parallel CPU jobs and smaller GPU jobs.

Official Docs: https://hyak.uw.edu/docs/klone/architecture
Onboarding: https://github.com/UWrc/klone-onboarding-cheme599a

## SSH setup

Set up your `~/.ssh/config` for easy access. The following will use a ssh key (`~/.ssh/id_ed25519`) for authentication so that you don't have to use your UW netid password every time (Only set this up if you're connecting from personal computer). It also caches Duo 2FA authentication for 24 hours so you won't have to do that every time either.

```
Host klone-login
    HostName klone.hyak.uw.edu
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
ssh-copy-id -i ~/.ssh/id_ed25519.pub klone-login
```

Now `ssh klone-login` should log you in without asking for a password, but will ask for Duo 2FA code (only once per 24 hours).

## Storage Setup

https://hyak.uw.edu/docs/storage/data

**Hyak Klone does not provide backup, persistent storage, or archival storage. All data on Klone exists as a single copy**

Note that the home directory (`/mmfs1/home/UWNetID`) has a 10GB limit.

If you've joined a group with a storage allocation you can use that. It's convenient to set environment variables for these commonly used paths:

```bash
export SCRATCH=/gscratch/scrubbed/$USER
export PROJECT=/gscratch/escience/$USER
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
export SCRATCH=/gscratch/scrubbed/$USER
export PROJECT=/gscratch/escience/$USER


export PIXI_HOME=$PROJECT/.pixi
export PIXI_CACHE_DIR=/tmp/cache/pixi

export PATH="$PIXI_HOME/bin:$PATH"
```

### Git / GitHub

git is already installed on klone, but the github cli is not. We install that with pixi and use it for github authentication:

```bash
pixi global install gh
gh auth login
```


## Check available resources

### storage

`hyakstorage`
```bash
                      Usage report for /mmfs1/home/scottyh
╭───────────────────┬────────────────────────────┬─────────────────────────────╮
│                   │ Disk Usage                 │ Files Usage                 │
├───────────────────┼────────────────────────────┼─────────────────────────────┤
│ Total:            │ 0GB / 10GB                 │ 22 / 256000 files           │
│                   │ 0%                         │ 0%                          │
╰───────────────────┴────────────────────────────┴─────────────────────────────╯
                   Usage report for /mmfs1/gscratch/escience
╭───────────────────┬────────────────────────────┬─────────────────────────────╮
│                   │ Disk Usage                 │ Files Usage                 │
├───────────────────┼────────────────────────────┼─────────────────────────────┤
│ Total:            │ 5903GB / 7168GB            │ 5320917 / 7000000 files     │
│                   │ 82%                        │ 76%                         │
│ My usage:         │ 0GB                        │ 235 files                   │
╰───────────────────┴────────────────────────────┴─────────────────────────────╯
```

### compute

`hyakalloc`
```bash
       Account resources available to user: scottyh
╭──────────┬──────────────┬──────┬────────┬──────┬───────╮
│  Account │    Partition │ CPUs │ Memory │ GPUs │       │
├──────────┼──────────────┼──────┼────────┼──────┼───────┤
│ escience │       cpu-g2 │   32 │   238G │    0 │ TOTAL │
│          │              │    0 │     0G │    0 │ USED  │
│          │              │   32 │   238G │    0 │ FREE  │
├──────────┼──────────────┼──────┼────────┼──────┼───────┤
│ escience │ cpu-g2-mem2x │   32 │   490G │    0 │ TOTAL │
│          │              │    0 │     0G │    0 │ USED  │
│          │              │   32 │   490G │    0 │ FREE  │
├──────────┼──────────────┼──────┼────────┼──────┼───────┤
│ escience │      gpu-a40 │   52 │   994G │    8 │ TOTAL │
│          │              │    0 │     0G │    0 │ USED  │
│          │              │   52 │   994G │    8 │ FREE  │
├──────────┼──────────────┼──────┼────────┼──────┼───────┤
│ escience │    gpu-rtx6k │   10 │    81G │    2 │ TOTAL │
│          │              │    0 │     0G │    0 │ USED  │
│          │              │   10 │    81G │    2 │ FREE  │
╰──────────┴──────────────┴──────┴────────┴──────┴───────╯
 Checkpoint Resources
╭───────┬──────┬──────╮
│       │ CPUs │ GPUs │
├───────┼──────┼──────┤
│ Idle: │ 5753 │  158 │
╰───────┴──────┴──────╯
```
