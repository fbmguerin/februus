# Comment fonctionne Februus

> **La référence est la version anglaise : [HOW-IT-WORKS.md](HOW-IT-WORKS.md).**
> Cette traduction peut avoir du retard ; en cas de différence, c'est
> l'anglais qui fait foi.

Une page, des mots simples. Si quelque chose n'est pas clair ici, c'est un
défaut de cette page : dites-le.

## Ce que ça fait

Un agent branche une clé USB sur la station. La station vérifie la clé
**sans ouvrir aucun fichier** et affiche une couleur :

- **Vert** : rien trouvé. La clé peut être utilisée.
- **Orange** : quelque chose d'inhabituel. Demandez de l'aide avant d'utiliser
  la clé.
- **Rouge** : danger, ou la station n'a pas pu vérifier. N'utilisez pas la clé.

Si quelque chose se passe mal (erreur, délai dépassé, clé débranchée, cas
inconnu), le résultat est **rouge**. La station ne dit jamais « vert » par
défaut.

## Ce qui se passe, étape par étape

```
 Clé USB branchée
        |
        v
 1. La station est prévenue (udev) et vérifie que l'appareil est autorisé (USBGuard)
        |
        v
 2. La clé est ouverte en LECTURE SEULE (udisks2) : pas d'écriture, aucun programme lancé
        |
        v
 3. Contrôle de la forme (« inspecteurs »), avant de lire le moindre fichier :
      - démarrable ?      la clé peut démarrer un ordinateur  -> rouge
      - système de fichiers ?  pas FAT32 / exFAT / NTFS       -> rouge
      - partitions ?      plus d'une                          -> orange
        |
        v
 4. Contrôle antivirus (ClamAV) : chaque fichier est lu comme de simples octets
        |
        v
 5. Verdict : la pire couleur gagne
        |
        v
 6. L'écran affiche vert / orange / rouge
        |
        v
 Clé débranchée -> l'écran revient à « en attente »
```

## Les éléments

| Élément | Rôle |
|---|---|
| `februus/scanner/` | Attend les événements USB et déroule les étapes ci-dessus (un seul service, `februus`, avec les écrans dedans) |
| `februus/inspectors/` | Contrôles de la forme (étape 3) |
| `februus/analyzers/clamav.py` | Contrôle antivirus (étape 4) |
| `februus/core/verdict.py` | Transforme les constats en une couleur (étape 5) |
| `februus/web/` | Les écrans que voit l'agent (étape 6) |
| `config/*.toml` | Tous les réglages, dont quel constat donne quelle couleur |
| `deploy/` | Script d'installation et réglages système d'une station |

## Constats et couleurs

Chaque contrôle renvoie des *constats*, chacun avec un code stable comme
`clamav.detected` ou `device.bootable`. Le fichier `config/februus.toml` dit
quelle couleur donne chaque code. Un code qui n'est pas dans le fichier donne
**rouge**. Pour rendre une règle plus stricte ou plus souple, il suffit de
changer un mot dans ce fichier.

## Règles de sûreté, en bref

1. Les fichiers de la clé ne sont jamais ouverts ni exécutés, seulement lus
   comme des octets.
2. Rien ne sort de la station (pas de nuage, pas d'analyse en ligne).
3. Le doute donne rouge.
4. La clé est montée en lecture seule. Rien n'est jamais écrit dessus.
5. La station n'utilise pas le réseau, sauf `freshclam`, qui télécharge les
   nouvelles signatures de virus. Les écrans n'écoutent que sur `127.0.0.1`.
6. Une ligne par clé est ajoutée à un fichier journal (verdict, nombre de
   fichiers, et noms des fichiers qui ont donné un avertissement), rien
   d'autre n'est gardé.
