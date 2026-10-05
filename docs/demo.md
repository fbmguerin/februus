# Démonstration au tuteur (T16)

Durée visée : 20 minutes, puis les questions. Deux versions :

- **A. Sans matériel** (Codespaces) : possible dès maintenant. Tout tourne
  sur des dossiers et des images de clé, avec le vrai ClamAV.
- **B. Sur le mini-PC** : après T14 et la validation matérielle
  (`docs/hardware-validation.md`). Mêmes étapes, avec de vraies clés.

Chaque étape indique ce qu'on montre, la commande (version A), le résultat
attendu et le message à faire passer.

## Préparation (la veille)

- [ ] Codespace reconstruit et à jour (`git pull`), `pip install -e .`
      fait.
- [ ] `pytest` : tout passe. `clamdscan --ping 1` répond `PONG` (sinon,
      lancer `clamd` et attendre une minute).
- [ ] Les images de démonstration : `python3 tools/demo-images.py ~/demo/images`.
- [ ] La configuration « avec ClamAV » (voir étape 3) dans `~/demo/clamav.toml`.
- [ ] Le port 8080 s'ouvre dans le navigateur (onglet « Ports » de
      Codespaces) ; navigateur en plein écran (F11) pour l'effet kiosque.
- [ ] L'affiche imprimée (`docs/poster/affiche-fr.html`, imprimer en A4
      avec les « graphiques d'arrière-plan »).
- [ ] Version B : le lot de clés de `docs/hardware-validation.md` (saine,
      EICAR, deux partitions, démarrable), étiquetées.

## 1. Le problème (2 min, sans écran)

- Les clés USB restent un vecteur d'attaque courant : virus, documents
  piégés, clés « démarrables », fausses clés qui se déclarent clavier.
- Une station blanche vérifie la clé **avant** qu'elle ne touche un poste.
- Cible : des agents non techniciens. Donc : zéro clic, un verdict en
  couleur, une consigne simple. L'affiche le résume.

## 2. L'accueil et le parcours d'une clé saine (3 min)

```sh
tools/demo.sh green
```

- Écran d'accueil : « Insérez votre clé USB », un conseil de sécurité qui
  change, la date des signatures antivirus (textes en français simple).
- Entrée : la clé est « insérée ». Barre de progression, temps restant,
  « Ne retirez pas la clé ».
- Résultat **vert** et son. Entrée : clé retirée, retour à l'accueil.

Message : *l'agent n'a rien à décider, seulement à lire une couleur.*

## 3. Un vrai virus de test avec ClamAV (3 min)

EICAR est un faux virus standard, reconnu par tous les antivirus et sans
danger. Il est généré au moment du test, jamais stocké dans le dépôt.

Configuration de développement avec ClamAV en plus de l'analyseur factice
(à préparer la veille) :

```sh
mkdir -p ~/demo/cle
sed -e 's/^enabled = \["fake"\]/enabled = ["fake", "clamav"]/' \
    -e "s|^path = \".*\"|path = \"$HOME/demo/keys.jsonl\"|" \
    config/februus.dev.toml > ~/demo/clamav.toml
cat >> ~/demo/clamav.toml <<'EOF'

[analyzers.clamav]
socket = "/run/clamav/clamd.ctl"
timeout_seconds = 120
EOF
februus config check -c ~/demo/clamav.toml
```

Pendant la démo :

```sh
echo "Rapport annuel" > ~/demo/cle/rapport.txt
februus scan -c ~/demo/clamav.toml ~/demo/cle        # VERT, code de sortie 0
ls -la ~/demo/cle                                    # rien n'a été ajouté sur la clé
python3 -c "from tests.samples import EICAR; open('$HOME/demo/cle/eicar.com','wb').write(EICAR)"
februus scan -c ~/demo/clamav.toml ~/demo/cle        # ROUGE : clamav.detected
ls -la ~/demo/cle                                    # seulement eicar.com, ajouté par nous
```

- Après le vert comme après le rouge : **rien n'est écrit sur la clé**
  (pas de fichier ajouté, rien de modifié).
- `februus stats -c ~/demo/clamav.toml` : les statistiques locales.

## 4. Les écrans qui comptent (3 min)

```sh
tools/demo.sh red     # rouge : alarme, « Retirez la clé et apportez-la… »
tools/demo.sh long    # « Ne retirez pas la clé. Revenez à HH:MM »
```

Avec `web.preview_screens = true` (configuration de développement), tous
les écrans sont visibles sans session :
http://127.0.0.1:8080/preview/removed (clé retirée trop tôt),
`/preview/orange`, `/preview/degraded` (station hors service).

Message : *retirer la clé trop tôt donne rouge. Une clé réinsérée repart
de zéro : on ne fait jamais confiance à une analyse interrompue.*

## 5. La clé elle-même, avant les fichiers (3 min)

Les « inspecteurs » lisent la clé brute, avant tout montage. Les images
ne contiennent que des tables de partitions et des secteurs de démarrage.

```sh
for i in ~/demo/images/*.img; do echo "== $i"; februus inspect -c config/februus.dev.toml "$i"; done
```

| Image | Résultat | Pourquoi |
|---|---|---|
| `clean-key.img` | vert | une clé FAT32 ordinaire |
| `two-partitions.img` | orange | plusieurs partitions (toutes sont analysées) |
| `bootable-iso.img` | rouge | ISO écrite avec `dd` : peut démarrer un PC |
| `efi-key.img` | rouge | partition système EFI : peut démarrer un PC |
| `linux-key.img` | rouge | système de fichiers non pris en charge (ext4) |

Message : *une clé démarrable est refusée sans même être montée.*

## 6. Échec = rouge (2 min)

Le point le plus important pour la sécurité : **le pire bug d'une station
blanche est un faux vert.**

```sh
rm ~/demo/cle/eicar.com   # la clé est de nouveau saine
pkill -x clamd     # (Codespaces) arrêter l'antivirus
februus scan -c ~/demo/clamav.toml ~/demo/cle
# ROUGE internal.error : "cannot connect to clamd" (clé saine, mais non vérifiée)
clamd              # le relancer
```

D'autres cas montrables dans les tests (`pytest -v -k "red or timeout"`) :
code de constat inconnu, fichier trop long à analyser, analyseur qui
plante, surveillance des clés arrêtée (écran « hors service », jamais un
ancien résultat).

## 7. L'architecture (4 min)

Montrer le schéma de `PLAN.md` (section 4.1) et insister sur :

- **Un seul service** : l'interface ne fait que lire l'état de la station
  (en mémoire), elle ne peut pas modifier un résultat.
- **Aucun code Februus en root.** Le montage est fait par udisks2 (service
  Debian maintenu) sous une règle polkit, en lecture seule, sans
  exécution. Les options réelles sont revérifiées dans le noyau
  (`/proc/self/mountinfo`).
- **USBGuard** n'accepte que des périphériques de stockage simples (pas de
  « clé » qui se déclare aussi clavier).
- **Rien ne quitte la station** : pas de VirusTotal, pas de cloud.
- **Tout est dans un fichier TOML** : couleur de chaque constat, délais,
  limites. `config/februus.example.toml`, `februus config check`.
- **Des contrôles simples** : un inspecteur est une fonction, un analyseur
  (macros, YARA) est un fichier de plus ; le cœur ne change pas.
- Qualité : environ 300 tests automatiques, intégration continue GitHub,
  plusieurs relectures du code.

## 8. La suite (1 min)

- Validation sur le mini-PC (`docs/hardware-validation.md`), puis T14 :
  démarrage automatique, kiosque, installation (`install.sh`).
- P2 : macros VBA/LibreOffice, YARA, signatures locales.
- P3 (avec le SIDSIC) : mails d'alerte, Zabbix, paquet `.deb`, miroirs
  internes. P4 : validation RSSI, RGPD, licence et dépôt publics.

## Questions probables

- **Pourquoi pas simplement un antivirus sur un PC ?** Le PC monterait la
  clé avec ses droits habituels (exécution possible, ouverture
  automatique). Ici la clé est montée en lecture seule sans exécution, sur
  une machine dédiée sans données ni réseau entrant, et l'agent n'a rien à
  décider.
- **Un seul antivirus, est-ce suffisant ?** Non, c'est un premier niveau.
  Le rouge « par défaut » couvre ce qu'il ne sait pas lire (archives
  chiffrées, PDF protégés). Les analyseurs P2 (macros, YARA) ajoutent des
  analyses sans changer le cœur.
- **Et si la clé est retirée et remplacée pendant l'analyse ?** Rouge
  immédiat, nouvelle session obligatoire.
- **Écrivez-vous quelque chose sur la clé ?** Non, jamais : la clé est
  montée en lecture seule et rien n'est ajouté dessus.
- **Pourquoi « orange » pour plusieurs partitions ?** Une clé du commerce
  n'en a qu'une ; plusieurs partitions peuvent cacher des données. Elles
  sont toutes analysées. La couleur se change dans le TOML.
- **Mise à jour des signatures ?** freshclam (Debian) ; un miroir interne
  est prévu au P3. L'écran d'accueil affiche la version des signatures.
- **Des données personnelles sont-elles conservées ?** Le journal local
  (une ligne par clé) garde le verdict, le nombre de fichiers et seulement
  les noms des fichiers qui ont provoqué un avertissement. La durée de
  conservation et la mention RGPD sont à fixer avec le DPO (P4).
