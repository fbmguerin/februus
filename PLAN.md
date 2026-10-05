# Februus — Plan

> Februus : dieu romain de la purification. Station blanche libre :
> analyse des clés USB, verdict vert / orange / rouge.

Version 0.2 — 4 octobre 2026. Explication simple : `docs/HOW-IT-WORKS.md`.
Avancement : `docs/STATUS.md`. Décisions : `docs/decisions.md`.

## 1. Objectif et principes

Un **démonstrateur 100 % fonctionnel** sur 5 postes de la préfecture,
utilisé par les agents. Moins parfait qu'un produit certifié, mais gratuit
et maintenu, contrairement aux solutions commerciales.

1. **Simple d'abord.** Peu de pièces, chacune explicable en deux lignes.
2. **Échec = rouge** (fail-closed) : erreur, délai, cas inconnu, clé retirée.
3. **Rien en dur** : couleurs, seuils, délais dans le TOML.
4. **Moindre privilège** : comptes séparés, pas de root, pas de réseau.
5. **Rien ne quitte la station**, rien n'est jamais écrit sur la clé.

## 2. Périmètre

**Maintenant (P1)** : clés et SSD USB (stockage de masse), FAT32 / exFAT /
NTFS en lecture seule, ClamAV (archives et PDF chiffrés, limites de taille
et de temps), inspection de la clé, verdicts configurables, écran kiosque en
français simple, progression + temps restant + « ne retirez pas la
clé », alerte de retrait, statistiques locales, USBGuard.

**Plus tard** (seulement après le démonstrateur) :
- P2 : macros VBA / LibreOffice, YARA, signatures supplémentaires, ext4.
- P3 : mails, syslog, Zabbix, paquet `.deb`, miroirs, déploiement de la
  config (Ansible), signal de vie.
- P4 : validation RSSI, PG-076, RGPD, licence, dépôt public. Fichier
  témoin signé si le besoin revient (il a été retiré, voir D16).

**Jamais** : nettoyer les fichiers, copier vers une autre clé, envoyer des
fichiers vers un service en ligne.

## 3. Comment ça marche

```
clé USB ─▶ USBGuard (refuse tout sauf stockage) ─▶ udev
  ─▶ scanner : montage lecture seule (udisks2, polkit)
       1. inspecteurs : clé amorçable ? format Windows ? partitions ?
       2. analyseur ClamAV : chaque fichier lu comme de simples octets
       3. verdict : la pire couleur gagne
  ─▶ écran web (kiosque) : vert / orange / rouge
```

| Pièce | Rôle |
|---|---|
| USBGuard, udev | Autoriser le stockage de masse, détecter insertion et retrait |
| udisks2 + polkit | Monter la clé `ro,noexec,nosuid,nodev` (aucun code Februus en root), options vérifiées dans mountinfo |
| `februus` (un seul service) | Pilote la session (inspecteurs, analyse, verdict, retrait) et sert les écrans |
| processus d'analyse | Fils du service : lit le contenu hostile, tué en cas de délai ou de retrait de la clé |
| `clamd` / `freshclam` | Antivirus Debian ; `freshclam` met à jour les signatures (seul à utiliser le réseau) |
| écrans (dans `februus`) | Avancement en direct (SSE), sons ; écoute `127.0.0.1` ; lit seulement l'état en mémoire |
| cage + Firefox | Kiosque verrouillé (`policies.json`), seulement `http://127.0.0.1` |

**Simplification (D16, STATUS)** : le fichier témoin, les traductions,
l'inspecteur `write_protect` (étape 2), les deux services et SQLite
(étape 3 : un seul service, état en mémoire, un journal d'une ligne par
clé) et le registre de plugins (étape 4 : les inspecteurs sont une liste
fixe de fonctions, les analyseurs se choisissent dans `[analyzers]`) sont
retirés.

### Inspecteurs (avant de lire un fichier)

| Code | Cas | Couleur |
|---|---|---|
| `device.bootable` | image amorçable, partition EFI ou BIOS boot | rouge |
| `device.boot_flag` | seulement le drapeau « actif » MBR | rouge (à ajuster après les vraies clés) |
| `filesystem.unsupported` | autre chose que FAT32 / exFAT / NTFS | rouge |
| `device.multi_partition` | plusieurs partitions | orange |

Une clé normale : une seule partition Windows. Plusieurs partitions toutes
Windows = orange ; amorçable ou format refusé = rouge (le pire gagne).

### Verdict

Table `[verdict.rules]` du TOML : code → `green` / `orange` / `red`. Code
absent = **rouge**. Exemples rouges : `clamav.detected`, `archive.encrypted`,
`pdf.encrypted`, `scan.limit_exceeded`, `scan.timeout`, `device.removed`,
`internal.error`. Voir `config/februus.example.toml`.

### Session

`IDLE → INSPECTING → MOUNTING → INVENTORY → SCANNING → VERDICT → RESULT`.
Un refus ou un échec donne `RESULT(rouge)`. **Retrait de la clé à tout
moment avant la fin** : `ABORTED`, rouge, alarme, « la clé N'A PAS été
vérifiée » ; une clé réinsérée repart de zéro. Si le temps restant dépasse
`long_scan_warning_minutes`, l'écran dit « Ne retirez pas la clé. Revenez à
HH:MM ».

### Configuration

`/etc/februus/februus.toml`, validé au démarrage (`februus config check`) ;
une config invalide empêche le démarrage. Peu de réglages, tous nécessaires.

### Sécurité de base

Debian 13 minimal sans bureau ; USBGuard ; montage lecture seule vérifié ;
analyse sans réseau avec délai et taille maximum ; Firefox verrouillé ;
aucun fichier de la clé n'est ouvert par une application ; pare-feu
nftables (rien en entrée sauf SSH d'administration).

## 4. Pile technique

Debian 13, Python 3.13 (paquets Debian, pas de pip sur la station), TOML
(`tomllib`), FastAPI + Jinja2 + uvicorn, journal d'une ligne par clé (JSON),
USBGuard + pyudev, clamav-daemon, cage + firefox-esr, pytest.

## 5. Dépôt

`februus/` : `core/` (session, verdict, config), `readers/`, `inspectors/`,
`analyzers/`, `analyzer/` (processus d'analyse), `scanner/`, `web/`. `config/`
(exemples TOML), `deploy/` (systemd, udev, polkit, USBGuard, kiosque,
`install.sh`), `tests/`, `docs/`.

## 6. Développement et tests

- **Claude Code web / Codespaces** : tout sauf l'USB réel ; le lecteur
  `directory` fait tourner le pipeline sur un dossier.
- **Poste de test** : USBGuard, udisks2, kiosque, vraies clés
  (`docs/hardware-validation.md`).
- Tests unitaires pytest ; tests ClamAV / matériel marqués et ignorés si
  indisponibles ; EICAR généré à l'exécution, jamais dans le dépôt ; CI =
  tests unitaires seulement.
- **Recette finale** (T15, poste Debian 13 minimal) : clé saine FAT32 /
  exFAT / NTFS, clé EICAR, plusieurs partitions, clé amorçable (ISO au `dd`),
  retrait pendant l'analyse, grosse clé (ETA), réinsertion.

## 7. Décisions clés

D1 une clé à la fois, pas de nettoyage · D2 Debian 13 durci · D3 Python ·
D4 TOML · D6 fail-closed · D7 montage par udisks2 + polkit, pas de service
root maison · D8 amorçable = rouge, plusieurs partitions = orange · D10
retrait pendant l'analyse = rouge, nouvelle session · D12 code en anglais,
commentaires critiques doublés en français · D13–D14 durcissement de
l'unité du service · D15 analyseurs sous leur propre compte (retiré à l'étape 3, voir D17).
**D16 (2026-10-04)** : projet de simplification : démonstrateur sur 5 postes,
sans fichier témoin, sans traductions, sans certification.
**D17 (2026-10-04)** : un seul service ; état en mémoire ; journal d'une ligne
par clé ; plus de service d'analyse séparé.
Détails et raisons : `docs/decisions.md`.
