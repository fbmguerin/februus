# Installer une station Februus (pas à pas, en copier-coller)

*[English version](INSTALL.md)*

> **La référence est la version anglaise : [INSTALL.md](INSTALL.md).**
> Cette traduction peut avoir du retard ; en cas de différence, c'est
> l'anglais qui fait foi.

Ce guide part d'un mini PC vide. Il suppose seulement que vous savez installer
Debian 13 (« Trixie »). Chaque bloc gris est à **copier-coller tel quel** dans
le terminal. Les mots entre `<` et `>` sont à remplacer.

Durée : environ 1 heure, dont une partie d'attente (téléchargements).

## Ce qu'il faut

- Un mini PC avec écran, clavier, souris, haut-parleur, et un câble réseau
  (Internet est nécessaire pour l'installation, puis pour mettre à jour les
  signatures de l'antivirus).
- Une clé USB d'installation de Debian 13.
- Le nom de la station : `f1`, `f2`, ... `f12` (sans zéro devant).
- Une clé USB de test (facultatif, pour vérifier à la fin).

## Étape 1 : installer Debian 13

Téléchargez l'installateur **`debian-13.7.0-amd64-netinst.iso`** (64 bits,
petit, le reste se télécharge pendant l'installation) sur
<https://www.debian.org/distrib/netinst> (un `13.x` plus récent convient) et
écrivez-le sur une clé USB (sous Linux : `sudo dd
if=debian-13.7.0-amd64-netinst.iso of=/dev/<la-cle> bs=4M status=progress
conv=fsync` ; sous Windows : Rufus, mode DD). **Vérifiez le nom de la clé
avant `dd` : il l'efface.**

Dans l'installateur de Debian :

1. Langue et clavier : français.
2. Nom de la machine : mettez le nom de la station (par exemple `f3`).
3. Mot de passe de `root` : choisissez-en un et notez-le. Créez aussi un
   utilisateur normal (par exemple `admin`).
4. Partitionnement : « Assisté, tout dans une seule partition » suffit pour
   essayer. Pour une vraie station : partitions séparées `/`, `/var`, `/tmp`,
   `/home` et swap, **sans LVM et sans chiffrement** (la station doit démarrer
   toute seule).
5. Choix des logiciels : **décochez tout** (surtout « environnement de
   bureau » et « GNOME »). Cochez seulement :
   - **serveur SSH** (pour administrer à distance) ;
   - **utilitaires usuels du système**.
6. Terminez et redémarrez sur le disque.

Pas de bureau, c'est voulu : la station affiche un seul écran, rien d'autre.

## Étape 2 : se connecter et passer administrateur

Connectez-vous (écran + clavier, ou en SSH depuis un autre PC), puis :

```
su -
```

Tapez le mot de passe de `root`. Le terminal doit afficher `root@...#`. **Toutes
les commandes suivantes se tapent en `root`.**

## Étape 3 : récupérer Februus

```
apt-get update
apt-get install -y git
git clone https://github.com/fbmguerin/februus.git /usr/local/src/februus
cd /usr/local/src/februus
```

Choisissez la version à installer :

```
git checkout main
```

## Étape 4 : première installation

**Débranchez tout ce qui est en USB sauf le clavier et la souris** (ni clé, ni
hub). L'installation autorise ces deux appareils-là, et seulement eux, en plus
des clés de stockage.

Remplacez `f3` par le nom de la station, puis lancez :

```
./deploy/install.sh --name f3 --usbguard
```

Cela installe les paquets Debian, l'antivirus ClamAV, le service Februus et
les règles de sécurité USB. Ça prend quelques minutes. À la fin, vous devez
voir une ligne `Active: active (running)`.

### Si le script dit « no ClamAV signatures yet »

C'est normal à la première installation : l'antivirus télécharge encore sa base
(quelques minutes). Attendez, vérifiez que des fichiers existent, puis relancez
la même commande :

```
ls /var/lib/clamav
./deploy/install.sh --name f3 --usbguard
```

La liste doit contenir des fichiers `.cvd` ou `.cld` (par exemple `daily.cld`).
Si elle reste vide après 15 minutes, regardez `journalctl -u clamav-freshclam`
(souvent : pas d'accès Internet).

## Étape 5 : vérifier que ça marche (sans écran de station)

```
systemctl status februus --no-pager
curl -s http://127.0.0.1:8080 | grep "<h1>"
```

Résultat attendu : `active (running)` puis `<h1>Insérez votre clé USB</h1>`.

Puis branchez une clé USB normale. Après quelques secondes :

```
curl -s http://127.0.0.1:8080 | grep "<h1>"
februus stats
```

Pour une clé sans problème, vous voyez `Aucune menace détectée` et `green: 1`.

### Essai avec un faux virus (facultatif)

EICAR est un fichier de test inoffensif que tous les antivirus reconnaissent.
Sur **un autre PC**, créez-le sur une clé **de test** (jamais sur une clé
importante) :

```
printf '%s%s' 'X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR' '-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*' > /media/<votre-cle>/eicar.com
```

(L'antivirus de cet autre PC peut protester : c'est normal.) Branchez la clé sur
la station : elle doit sortir **rouge** (`Un virus ou un fichier malveillant a été trouvé`).

## Étape 6 : installer l'écran de la station (kiosque)

L'écran affiche en plein écran vert / orange / rouge, avec les sons. Il est
installé avec Firefox et `cage` (un mini-gestionnaire de fenêtres).

```
./deploy/install.sh --kiosk
reboot
```

Au redémarrage, l'écran « Insérez votre clé USB » doit apparaître tout seul.

> Le kiosque a été essayé dans une fenêtre, **pas encore au démarrage d'un PC
> sans bureau** (voir `docs/hardware-validation.md`, section 8). Si l'écran
> reste noir, connectez-vous en SSH et regardez
> `journalctl -u februus-kiosk -b` ; la station elle-même (l'analyse des clés)
> continue de marcher.

Pour rendre le tout encore plus propre, faites ensuite les contrôles des
sections 7 et 8 de `docs/hardware-validation.md` (écrivez les résultats dans la
colonne « Result »).

## Facultatif : l'apparence de votre site (thème)

Les écrans peuvent prendre l'apparence d'un lieu (logo, couleurs, polices) avec
un dossier de *thème*, sans changer le code : `sudo ./deploy/install.sh --theme
/chemin/du/theme`. Voir `deploy/theme-example/`. Un thème qui utilise une marque
officielle (par exemple le système de design de l'État) doit rester dans son
propre dépôt privé, pas dans ce dépôt public.

## Utilisation par un agent

1. Brancher **une** clé (le mini PC est caché, on utilise la rallonge USB).
2. Attendre l'écran : vert (rien trouvé), orange (inhabituel, demander de
   l'aide) ou rouge (ne pas utiliser la clé).
3. Retirer la clé quand l'écran le dit.

Une seule clé à la fois : si on en branche une deuxième, un message demande de
la retirer. Les hubs USB sont bloqués volontairement : une clé se branche
directement.

## Mettre à jour plus tard

```
cd /usr/local/src/februus
git pull
./deploy/install.sh
```

Le script peut être relancé sans risque. Il garde la configuration
(`/etc/februus/februus.toml`) et le journal des clés. Si une nouvelle version
exige un nouveau réglage, il s'arrête **sans rien casser** et affiche quoi
corriger (comparez avec `config/februus.example.toml`).

## En cas de problème

| Symptôme | Que faire |
|---|---|
| Écran « Station hors service » | `systemctl restart februus` puis `journalctl -u februus -n 50` |
| La clé n'est jamais vue | Elle est peut-être derrière un hub (bloqué), ou ce n'est pas une clé de stockage pur. Message « Un appareil USB a été bloqué » à l'écran dans ce cas |
| Toutes les clés sortent rouges avec « La station n'a pas pu terminer l'analyse » | `journalctl -u februus -n 100` ; vérifier `systemctl status clamav-daemon` ; prévenir la personne qui gère le projet avec les lignes du journal |
| Clé rouge « already mounted » | Retirer la clé, attendre 5 secondes, la rebrancher |
| Voir ce qui s'est passé | `journalctl -u februus -f` (en direct), `februus stats`, `cat /var/log/februus/keys.jsonl` |
| Clavier ou souris bloqué après `--usbguard` | Le script le détecte et remet les anciennes règles tout seul. Sinon : `systemctl stop usbguard` |
| Changer le nom de la station | `./deploy/install.sh --name f4` |

## Ce que l'installation a mis sur le PC

- le code dans `/opt/februus` (en lecture seule pour les services) ;
- la commande `februus` ;
- la configuration `/etc/februus/februus.toml` (ne la changez pas sans raison) ;
- un seul service, `februus` (les écrans sur `http://127.0.0.1:8080`, local à
  la machine) ;
- le journal des clés `/var/log/februus/keys.jsonl` (une ligne par clé) ;
- les règles USB (USBGuard), udev, udisks2 et polkit ;
- avec `--kiosk` : le service `februus-kiosk` et les règles de Firefox qui
  n'autorisent que l'écran de la station.

Le détail du fonctionnement : `docs/HOW-IT-WORKS.fr.md`. Les décisions :
`docs/decisions.md`.
