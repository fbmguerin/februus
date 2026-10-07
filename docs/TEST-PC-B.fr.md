# Plan de test : second mini PC (« PC B »)

*[English version](TEST-PC-B.md)*

> **La référence est la version anglaise : [TEST-PC-B.md](TEST-PC-B.md).**
> Cette traduction peut avoir du retard ; en cas de différence, c'est
> l'anglais qui fait foi.

But : prouver qu'une station installée **de zéro, avec le seul guide
d'installation**, fonctionne comme la vraie (sans bureau, écran kiosque, vraies
clés, un agent qui ne connaît pas le projet). Compter 4 à 5 heures, avec une
personne pour brancher les clés. Le guide d'installation
([INSTALL.fr.md](INSTALL.fr.md)) **fait partie du test** : chaque étape floue
ou en échec est un défaut du guide, à noter et à corriger.

Les résultats vont dans les colonnes « Result » de
[hardware-validation.md](hardware-validation.md), écrits sous la forme
`PC B 2026-10-xx : OK / KO + remarques`. N'écrivez jamais un résultat qui n'a
pas été vu. Les contrôles gardent leurs numéros (2.3, 7.12...) ; ce plan donne
l'ordre.

## 0. À apporter

| Matériel | Pourquoi |
|---|---|
| PC B, écran, haut-parleur, clavier, souris, câble réseau | la station |
| Clé USB avec `debian-13.7.0-amd64-netinst.iso` (l'installateur) | installation |
| **Deux clés USB de test** (1 Go ou plus, 8 à 32 Go convient), **qui seront effacées** | les contrôles (section 1) |
| Rallonge USB | usage réel (le PC sera caché) |
| 10 clés ordinaires de la préfecture (saines, **non effacées** : seulement branchées) | contrôle 5.3 |
| Un téléphone, un second clavier USB, le hub USB | USBGuard (5.2, 5.4, 5.5) |
| L'affiche imprimée (`docs/poster/affiche-fr.html`) | recette avec un agent |
| Une personne qui ne connaît pas le projet | phase 8 |

Aucun second PC n'est nécessaire : les clés de test se préparent sur le PC B
lui-même.

## 1. Les clés de test : deux suffisent (on charge un « kit » pour chaque test)

Au lieu de 12 clés, **deux** clés sont rechargées autant de fois qu'il faut avec
`tools/load-test-key.sh` (après l'installation du guide, le dépôt est dans
`/usr/local/src/februus`). L'outil efface la clé, puis y écrit les fichiers d'un
kit. Par sécurité, il refuse tout ce qui n'est pas une petite clé USB amovible
sans rien de monté, et demande de retaper le nom du périphérique. En root
(`su -`) :

```
cd /usr/local/src/februus
lsblk -o NAME,SIZE,MODEL,TRAN       # repérer la clé : /dev/sdb par exemple (pas une partition !)
tools/load-test-key.sh /dev/sdb eicar
```

Puis **débranchez la clé et rebranchez-la** : la station l'analyse. Attendez la
fin (le résultat reste à l'écran) avant de charger un autre kit. La **clé A**
sert aux kits l'un après l'autre ; la **clé B** reste pour les tests à deux clés
et ceux d'USBGuard.

| Kit | Commande (`/dev/sdb` = la clé) | Attendu |
|---|---|---|
| saine FAT32 (26 fichiers ordinaires) | `tools/load-test-key.sh /dev/sdb clean` | **vert** (2.2) |
| NTFS, exFAT | `... ntfs`, `... exfat` | **vert** |
| EICAR | `... eicar` | **rouge** `clamav.detected` (2.3, 7.3) |
| EICAR dans un zip | `... eicar-zip` | **rouge** `clamav.detected` |
| zip et PDF chiffrés | `... encrypted` | **rouge** `archive.encrypted`, `pdf.encrypted` |
| zip trop imbriqué | `... nested` | **rouge** `scan.limit_exceeded` |
| deux partitions saines | `... two-partitions` | **orange** `device.multi_partition` (2.4) |
| deux partitions, EICAR sur la seconde | `... two-partitions-eicar` | **rouge**, chemin `sdb2/...` |
| fichier de 900 Mo | `... big` | analyse longue, temps restant, test de retrait (3.1, 3.2) |
| fichier de 1,1 Go | `... toobig` | **vert** depuis la limite de 2 Go (environ 1 minute) ; un fichier de plus de 2 Go est rouge `file.too_big` tout de suite |
| vraie ISO amorçable | `... iso /root/debian-13.7.0-amd64-netinst.iso` | **rouge** `device.bootable`, jamais montée (2.5) |

Pour l'ISO : `curl -fL -o /root/debian-13.7.0-amd64-netinst.iso
https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/debian-13.7.0-amd64-netinst.iso`
(ou le fichier de la clé d'installation).

**Contrôle 2.10 (rien d'écrit sur la clé).** L'outil enregistre le `sha256sum`
des fichiers dans `/root/test-keys/<kit>.sha256`. Une fois la clé analysée par la
station et le résultat affiché, comparez (en lecture seule) :

```
mkdir -p /mnt/k && mount -o ro /dev/sdb1 /mnt/k
(cd /mnt/k && sha256sum --quiet -c /root/test-keys/clean.sha256 && echo TOUT-IDENTIQUE)
umount /mnt/k
```

Attendu : `TOUT-IDENTIQUE` (toute différence est listée à la place).

**À savoir.** Une clé qui a contenu une ISO et qui a seulement été reformatée
reste **rouge** (`device.bootable`) : l'enregistrement de démarrage de l'ISO
reste dans l'espace vide avant la première partition. L'outil efface les 16
premiers Mo pour cette raison ; un formatage rapide ne le fait pas.

## 2. Les phases

| N° | Phase | À faire | Contrôles | Durée |
|---|---|---|---|---|
| 1 | Installer Debian | [INSTALL.fr.md](INSTALL.fr.md) étapes 1-2 (sans bureau ; noter tout ce qui est flou) | — | 30 min |
| 2 | Installer Februus | étapes 3-5, avec `--name f<N> --usbguard`, seuls clavier et souris branchés. **Noter les minutes de chaque étape** (l'attente de freshclam !) | 6.1-6.3, 7.1, 7.2, 7.11 | 40 min |
| 3 | Clés | les kits de la section 1, un par un sur la clé A : voir l'écran, `februus stats`, `mountinfo` après chacun ; contrôle 2.10 avec les empreintes enregistrées | 2.1-2.10, 7.3, 7.4, 7.9, 7.10, 5.3 (les 10 clés ordinaires) | 60 min |
| 4 | Appareils bloqués | téléphone, second clavier, hub : le message s'affiche, la clé derrière le hub n'est pas vue. Deux clés à la fois (3.6, 3.7) | 5.1, 5.2, 5.4, 5.5, 3.6, 3.7 | 20 min |
| 5 | Robustesse | clé retirée pendant l'analyse (kit `big` : 3.1, 3.2), réinsertion immédiate (3.5), `kill -9` (7.7), délai dépassé (7.5), `systemctl stop` (7.8), **coupure de courant pendant une analyse** (débrancher le PC, redémarrer : le service démarre, la clé encore branchée est réanalysée, aucune erreur de système de fichiers), câble réseau débranché (la station continue de marcher) | 2.9, 3.x, 7.5-7.8 | 45 min |
| 6 | Kiosque | étape 6 du guide, redémarrage. Écran au démarrage, sons (vert, orange, rouge, alarme) entendus par une personne, raccourcis clavier (Ctrl+L, Ctrl+T, F11, Ctrl+Alt+F3) sans moyen de sortir | 7.12, 8.1-8.7 | 40 min |
| 7 | Thème | « Thème de la préfecture de la Moselle » du guide (**lire l'avertissement**), puis vérifier tous les écrans avec les clés de la phase 3 (attente, analyse, vert, orange, rouge, clé retirée, deux clés, appareil bloqué) | — | 25 min |
| 8 | Recette avec un agent | une personne qui ne connaît pas le projet, avec la seule affiche, sans aide : les kits `clean` (vert), `eicar` (rouge), puis elle retire la clé pendant l'analyse du kit `big`. Noter les hésitations et les fausses interprétations | T15 | 20 min |
| 9 | Clôture | `tools/station-report.sh` (en root) après les phases ; écrire les résultats ; commiter les corrections du guide | — | 20 min |

En root (`su -`), lancez `tools/station-report.sh > /root/rapport-phase<N>.txt` à la fin de
chaque phase : c'est un instantané en lecture seule (services, âge des
signatures, appareils USBGuard, montages, dernières clés, journal). Collez-le
dans un message pour obtenir de l'aide.

## 3. Réussite ou échec

**Doit passer** (un échec interdit d'utiliser la station) :

| Règle | Contrôle |
|---|---|
| Rien n'est jamais écrit sur une clé (empreintes identiques avant et après) | 2.10 |
| Tout échec est rouge (clé retirée, délai, limite, chiffré, amorçable, illisible) | 2.3-2.5, 3.x, 7.5, 7.6 |
| EICAR est trouvé, même dans une archive | 2.3, 7.3 |
| Les clés sont montées `ro,noexec,nosuid,nodev` et rien ne reste monté | 1.x, 2.8 |
| Les hubs et les appareils qui ne sont pas des clés sont bloqués, clavier et souris marchent encore | 5.1, 5.2, 5.4 |
| La station démarre seule après un redémarrage et après une coupure de courant | 7.12, phase 5 |
| Un agent sans aide comprend vert / rouge | phase 8 |
| Dans le kiosque, aucun moyen d'ouvrir une autre page ni un terminal | 8.6 |

**Devrait passer** (à corriger, sans bloquer) : sons, détails du thème, durées
du guide, formulation des écrans.

**S'arrêter et signaler tout de suite** (ne pas réparer à la main) : toutes les
clés donnent `internal.error` ; une clé est modifiée ; un clavier ou une souris
est bloqué et le PC ne peut plus être administré.

## 4. Journal des difficultés du guide

À remplir pendant les phases 1-2 et 6-7 (une ligne par problème, puis corriger
le guide).

| Étape du guide | Ce qui était flou ou a échoué | Correction |
|---|---|---|
|  |  |  |

## 5. Aide à distance (facultatif)

Avec le serveur SSH choisi à l'installation, les commandes peuvent être lancées
depuis un autre PC (`ssh admin@<adresse>`, puis `su -`), ce qui laisse l'écran du
kiosque tranquille. Pour demander de l'aide, collez le résultat de
`tools/station-report.sh` et le message exact.
