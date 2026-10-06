# Februus

**[Installer une station : guide pas à pas](docs/INSTALL.fr.md)** · *[English version](README.md)*

> **La référence est la version anglaise : [README.md](README.md).**
> Cette traduction peut avoir du retard ; en cas de différence, c'est
> l'anglais qui fait foi.

Station blanche USB libre : analyse les clés USB (ClamAV, YARA, VBA, macros LibreOffice) et donne un verdict simple vert / orange / rouge. Conçue pour les administrations et les écoles.

> **État : prototype P1, pas prêt pour la production.** La chaîne d'analyse
> et les écrans sont écrits et testés. La gestion de l'USB (service de
> surveillance, montage udisks2, règles système, USBGuard) a passé une
> première série de contrôles sur un PC de test avec de vrais appareils
> ([docs/hardware-validation.md](docs/hardware-validation.md), en anglais) ;
> certains contrôles restent à faire. L'installateur et le service existent ;
> l'écran kiosque n'est pas encore testé au démarrage. Avancement :
> [docs/STATUS.md](docs/STATUS.md).

## Ce que ça fait

Un agent branche une clé USB sur la station. Sans aucun clic, la station :

1. **inspecte la clé elle-même** : partitions, code de démarrage, système de
   fichiers. Une clé qui peut démarrer un ordinateur est refusée avant la
   lecture du moindre fichier ;
2. **la monte en lecture seule** (`ro,noexec,nosuid,nodev`) et liste ses
   fichiers ;
3. **analyse chaque fichier** avec ClamAV, un par un, avec une barre de
   progression et le temps restant ;
4. **affiche un verdict** :

| Couleur | Signification | Ce que fait l'agent |
|---|---|---|
| Vert | Aucune menace trouvée | Utilise la clé |
| Orange | Vérifiée, avec des réserves (plusieurs partitions...) | Utilise la clé avec prudence |
| Rouge | Menace trouvée, ou clé impossible à vérifier entièrement | N'utilise pas la clé, la porte au support informatique |

Rien n'est jamais écrit sur la clé.

Si la clé est retirée avant la fin, le résultat est rouge : une clé qui n'a
pas été entièrement vérifiée n'est jamais crue.

## Principes de sécurité

- **Échec = rouge (« fail-closed »).** Toute erreur, tout dépassement de temps
  ou cas inconnu donne rouge. Le pire défaut d'une station blanche est un
  faux vert.
- **Les fichiers sont seulement lus comme des octets.** Rien de ce qui vient
  de la clé n'est exécuté, ouvert ou affiché, et rien n'est écrit dessus.
- **Rien ne sort de la station.** Aucun service dans le nuage, aucun fichier
  envoyé nulle part.
- **Aucun code Februus ne tourne en root.** Le montage est fait par udisks2
  (service système Debian) sous une règle polkit ; les vraies options de
  montage sont vérifiées dans `/proc/self/mountinfo`.
- **Moindre privilège.** Le scanner, les analyseurs et l'interface web
  tournent sans privilège ; l'interface web ne fait que lire l'état de la
  station.
- **USBGuard** n'accepte que les appareils de stockage purs (pas de clavier
  caché dans une clé).

## Architecture

```
Clé USB ─▶ USBGuard ─▶ ┌──────── februus serve (un seul service) ──────┐
                       │ scanner ◀──D-Bus──▶ udisks2 + polkit          │
                       │    │  (montage en lecture seule)              │
                       │    ├─ processus d'analyse ─▶ clamd            │
                       │    ▼                                          │
                       │ état (mémoire) ◀── lecture seule ── écrans web│──▶ navigateur kiosque
                       └─────────────────────────────┬─────────────────┘
                                                     ▼
                                  journal des clés : une ligne par clé
```

- **`februus serve`** : un service, un processus. Un fil d'exécution suit les
  événements USB (pyudev) et lance une session par clé ; le fil principal
  sert les écrans du kiosque (FastAPI, Jinja2, progression en direct par
  Server-Sent Events), en français simple. Les écrans ne font que lire
  l'état de la station, gardé en mémoire.
- **Processus d'analyse** : un processus enfant qui lit le contenu du fichier
  et interroge ClamAV ; il est tué si un fichier prend trop de temps ou si la
  clé est retirée.
- **Journal des clés** : une ligne JSON par clé
  (`/var/log/februus/keys.jsonl`), lue par `februus stats`.
- **Les contrôles** sont de simples fichiers Python :
  - les *inspecteurs* regardent la clé brute (`partitions`, `bootable`,
    `filesystem`) : une fonction chacun, exécutées dans une liste fixe
    (`februus/inspectors/__init__.py`) ;
  - les *analyseurs* vérifient chaque fichier (`clamav` ; `fake` pour le
    développement) : le TOML (`[analyzers] enabled`) choisit lesquels
    tournent ;
  - les *lecteurs* donnent accès aux fichiers : `kernel_mount` sur une
    station, `directory` pour le développement (choisi par la commande, pas
    par le TOML).
- **Règles de verdict** : les contrôles renvoient des codes de constat
  (`clamav.detected`, `device.bootable`...) ; la configuration associe une
  couleur à chaque code. Un code inconnu est rouge, la pire couleur gagne.

Détails et décisions de conception : [PLAN.md](PLAN.md), section 4.

## Essayer sans clé USB

Toute la chaîne tourne sur un dossier, avec une configuration de
développement (lecteur `directory`). Il faut : Debian 13 (ou le devcontainer
Codespaces de ce dépôt), Python 3.13 et les paquets Debian
`python3-fastapi python3-uvicorn python3-jinja2 python3-pyudev`.

```sh
pip install -e .                                    # une fois, dans un venv
februus config check -c config/februus.dev.toml    # valider la configuration
februus scan -c config/februus.dev.toml <dossier>  # analyser un dossier
tools/demo.sh green                                 # démo en direct des écrans
```

`tools/demo.sh` lance l'interface web sur http://127.0.0.1:8080 et simule une
clé (`green`, `red`, ou `long` pour l'écran « revenez à HH:MM »). La
configuration de développement utilise un faux analyseur : pas besoin de
ClamAV. Avec clamd en route, `pytest -m clamav` lance les tests ClamAV
(EICAR est généré à l'exécution, jamais stocké dans le dépôt).

Autres commandes : `februus --help`, et la liste dans [AGENTS.md](AGENTS.md)
(« Commands »).

## Installer une station

**Guide pas à pas, en copier-coller : [docs/INSTALL.fr.md](docs/INSTALL.fr.md)**
([in English](docs/INSTALL.md)).

Sur Debian 13, en root (`su -`), depuis une copie du dépôt :

```
deploy/install.sh --name f3    # première installation : nom de la station
deploy/install.sh              # paquets, comptes, règles, services
deploy/install.sh --usbguard   # aussi les règles USBGuard : les appareils
                               # branchés maintenant (clavier, souris) sont
                               # les seuls appareils hors stockage autorisés
```

Les stations s'appellent f1, f2, ... f12 (sans zéro devant). `--name` donne le
nom de la machine (hostname), affiché sur les écrans ; sans cette option, le
nom actuel est gardé.

Le script peut être relancé après chaque mise à jour. Il installe le code dans
`/opt/februus`, la commande `februus`, la configuration
`/etc/februus/februus.toml` (gardée si elle existe) et un seul service,
`februus` (écrans sur http://127.0.0.1:8080). L'ancienne installation à trois
services n'est PAS encore vérifiée sur la nouvelle organisation ; l'ancienne
a été vérifiée sur un PC de test ; voir
[docs/hardware-validation.md](docs/hardware-validation.md).

Pas encore terminé : l'écran kiosque (`--kiosk` : cage + Firefox, essayé dans
une fenêtre, pas au démarrage). Système visé : Debian 13 minimal, sans bureau,
sur un petit PC avec un écran et un haut-parleur. Les fichiers système sont
dans [`deploy/`](deploy/) (unités systemd, udev, udisks2, polkit, USBGuard,
réglages de clamd).

## Configuration

Un seul fichier TOML, `/etc/februus/februus.toml`, identique sur chaque
station (surcharges locales dans `/etc/februus/conf.d/*.toml`). Chaque clé est
obligatoire et validée au démarrage : `februus config check`. Exemple commenté :
[config/februus.example.toml](config/februus.example.toml).

## Développement

- Tests : `pytest` (tests unitaires, aussi lancés par GitHub Actions) ;
  `pytest -m clamav` et `pytest -m hardware` demandent clamd ou une vraie clé.
- Règles pour les contributeurs et les agents de code : [AGENTS.md](AGENTS.md).

## Documentation

| Document | Contenu |
|---|---|
| [docs/INSTALL.fr.md](docs/INSTALL.fr.md) | Installer une station, pas à pas |
| [docs/HOW-IT-WORKS.fr.md](docs/HOW-IT-WORKS.fr.md) | Explication simple du fonctionnement |
| [docs/STATUS.md](docs/STATUS.md) | Avancement, décisions, questions ouvertes (en anglais) |
| [PLAN.md](PLAN.md) | Plan du projet et architecture (en français) |
| [docs/hardware-validation.md](docs/hardware-validation.md) | Contrôles à passer sur la vraie station (en anglais) |
| [docs/poster/](docs/poster/) | Affiche pour les utilisateurs, à imprimer à côté de la station |
| [docs/demo.md](docs/demo.md) | Script de démonstration (en français) |

## Licence

[MIT](LICENSE) (texte officiel en anglais). Composants tiers et leurs
licences (paquets Debian, police des écrans) :
[docs/CREDITS.md](docs/CREDITS.md).

## Pourquoi « Februus » ?

Le nom **Februus** renvoie au dieu romain associé à la purification, à
l'expiation et aux enfers. Le mois de février (*Februarius*) tirerait son nom
de cette figure et des rites de purification célébrés à cette période.

Comme Februus, le projet Februus veut **purifier** les supports amovibles : il
inspecte les clés USB, détecte les menaces et donne un verdict simple avant
leur utilisation dans les écoles et les administrations.

En savoir plus : [Februus - Wikipedia](https://wikipedia.org/wiki/Februus)
