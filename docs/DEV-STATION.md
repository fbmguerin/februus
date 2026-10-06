# Prepare a development and test PC (like f1)

> **Résumé en français.** Ce guide prépare un PC de développement et de test
> (comme f1) : Debian 13 minimale, quelques outils (git, gh, pytest, httpx,
> tmux), une locale UTF-8, le dépôt cloné dans le dossier personnel et
> installé en root (`su -`) depuis ce clone, le groupe `adm` pour lire les
> journaux, un accès GitHub et un accès distant **temporaires**. **Rien de
> tout cela ne doit se trouver sur une station de production** : à la fin,
> suivez la liste de nettoyage, puis réinstallez le PC proprement avec
> [INSTALL.fr.md](INSTALL.fr.md). La version anglaise ci-dessous fait foi.

A development PC is a real station (same mini PC, same Debian, same
`deploy/install.sh`) on which someone also edits the code, runs the tests and
pushes to GitHub. Use it to try a change on real hardware (kiosk, keys,
USBGuard) before it reaches the stations.

> **WARNING. Never on a production station.** The GitHub access, the remote
> access, the developer tools and the working copy of the repository give a
> way into the station and to the repository. A station used by the agents is
> installed with [INSTALL.md](INSTALL.md) only. When the tests are over,
> follow the [clean-up list](#clean-up-before-the-pc-becomes-a-station).

## 1. Debian and tools

Install Debian 13 as in [INSTALL.md](INSTALL.md), steps 1 and 2 (no desktop;
"SSH server" and "standard system utilities" only), with a normal user (here
`f1`). There is no sudo: commands for root are typed in `su -`.

As root (`su -`), add only:

```
apt-get install -y git gh python3-pytest python3-httpx tmux
usermod -aG adm f1
```

`adm`: the user can read the journals (`journalctl -u februus`) without being
root. Log out and in again for it to apply. The other Python packages
(FastAPI, Jinja2, pyudev...) come with `deploy/install.sh`: before it, the
tests that need them fail at import.

## 2. UTF-8 text

An SSH session can arrive with the locale `C` (plain ASCII): the accents of
the French texts and the borders of tmux then show as `?` or `_`. Check, as
the user:

```
locale | head -1
```

If it does not say `UTF-8`, add this line to `~/.profile`, then log in again:

```
export LANG=C.UTF-8
```

(`C.UTF-8` always exists on Debian, nothing to generate.)

## 3. GitHub access (temporary)

As the user (not root):

```
gh auth login        # GitHub.com, HTTPS, log in with a web browser (a code to type)
gh auth setup-git
git clone https://github.com/fbmguerin/februus.git ~/februus
git -C ~/februus config user.name "<Your Name>"
git -C ~/februus config user.email "<your GitHub noreply address>"
```

Use the account of the project only, and touch only its repositories.

## 4. Install Februus from the clone

The clone is in the home folder; `deploy/install.sh` copies the code to
`/opt/februus`, so the clone can change without touching the running station.
Unplug every USB device except the keyboard (and the mouse) if you use
`--usbguard`. As root (`su -`):

```
/home/f1/februus/deploy/install.sh --name f1 --usbguard --kiosk
```

After a change of the code: as the user, `git pull` (or your branch), then as
root the same command again (without `--usbguard`: the devices plugged in at
that moment would become the allowed ones).

Tests, as the user: `cd ~/februus && pytest`.

## 5. Remote access (temporary)

SSH on the local network is enough. If the PC is elsewhere, a VPN tool (for
example Tailscale) can be added for the test period only. Work inside `tmux`
so a lost connection does not stop a long command.

## Clean up before the PC becomes a station

Do all of this, in order, when the tests are over:

1. **Revoke the GitHub CLI access**: on
   <https://github.com/settings/applications>, tab "Authorized OAuth Apps",
   "GitHub CLI", **Revoke**. On the PC: `gh auth logout`.
2. **Delete the SSH key of the PC** on GitHub, if one was added:
   <https://github.com/settings/keys>. On the PC: `rm ~/.ssh/id_*`.
3. **Remove the remote access**: uninstall the VPN tool and remove the machine
   from its admin console; remove the SSH keys of other PCs from
   `~/.ssh/authorized_keys`.
4. **Reinstall the PC cleanly**: a fresh Debian 13, then [INSTALL.md](INSTALL.md)
   only (clone in `/usr/local/src/februus`, no developer tools, no `adm` for a
   normal user). Do not "clean" a development PC and use it as a station.
