"""Textes affichés à l'écran pour chaque code de constat (français simple).

Un code absent d'ici est quand même affiché, avec un message générique : la
couleur d'un code ne dépend jamais de ce fichier (elle vient des règles du
TOML).
"""

# Conseils de sécurité affichés à tour de rôle sur l'écran d'attente
# (à faire valider par la préfecture).
TIPS = (
    "Ne branchez jamais une clé USB trouvée par hasard : apportez-la à votre support informatique.",
    "Un résultat vert ne remplace pas la prudence : n'ouvrez pas de fichiers inattendus.",
    "Vérifiez ici chaque clé USB avant de l'utiliser sur un ordinateur de travail.",
    "Un document qui vous demande d'activer les macros est suspect.",
    "Signalez toute clé USB suspecte à votre support informatique.",
)

FINDING_MESSAGES = {
    "clamav.detected": "Un virus ou un fichier malveillant a été trouvé.",
    "archive.encrypted": "Une archive est protégée par un mot de passe : elle ne peut pas être vérifiée.",
    "pdf.encrypted": "Un PDF est protégé par un mot de passe : il ne peut pas être vérifié.",
    "scan.limit_exceeded": "Un fichier est trop gros ou trop complexe pour être vérifié.",
    "file.too_big": "Un fichier est trop gros pour être vérifié (vidéo, sauvegarde, image disque...).",
    "scan.timeout": "L'analyse a pris trop de temps et a été arrêtée.",
    "device.refused": "Cet appareil n'est pas accepté par la station.",
    "device.bootable": "Cette clé peut démarrer un ordinateur : elle est refusée.",
    "device.boot_flag": "Cette clé est marquée comme pouvant démarrer un ordinateur.",
    "device.removed": "La clé a été retirée pendant l'analyse.",
    "filesystem.unsupported": "Le format de cette clé n'est pas pris en charge.",
    "internal.error": "La station n'a pas pu terminer l'analyse.",
    "device.multi_partition": "Cette clé contient plusieurs partitions.",
    "file.not_regular": "La clé contient des fichiers spéciaux (liens, périphériques).",
    "macro.benign": "Un document contient des macros.",
    "macro.suspicious": "Un document contient des macros suspectes.",
}
