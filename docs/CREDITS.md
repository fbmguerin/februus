# Credits and third-party components

Februus itself is under the [MIT licence](../LICENSE). Nothing below is copied
into the repository except the font. The
programs are installed from Debian 13 packages by `deploy/install.sh`; Februus
does not link them into its own code and does not redistribute them, so their
licences do not apply to Februus (checked in `/usr/share/doc/<package>/copyright`
on 2026-10-05).

| Component | Debian package | Licence | How Februus uses it |
|---|---|---|---|
| FastAPI | `python3-fastapi` | MIT (Expat) | imported (the screens) |
| Uvicorn | `python3-uvicorn` | BSD-3-Clause | imported (web server) |
| Jinja2 | `python3-jinja2` | BSD-3-Clause | imported (templates) |
| pyudev | `python3-pyudev` | LGPL-2.1+ | imported as a library (unmodified, replaceable) |
| ClamAV (clamd, freshclam) | `clamav-daemon`, `clamav-freshclam` | GPL-2 | separate process, talked to through a socket |
| udisks2 | `udisks2` | GPL-2+ / LGPL-2+ | separate service, used through `udisksctl` |
| polkit | `polkitd` | LGPL-2+ / MIT | system service (one rule file) |
| USBGuard | `usbguard` | GPL-2+ | separate service (one rules file) |
| cage (kiosk) | `cage` | MIT | separate program |
| Firefox ESR (kiosk) | `firefox-esr` | MPL-2.0 (and others) | separate program, one policy file |
| DejaVu Sans | `fonts-dejavu-core` | Bitstream Vera / public domain | system font, not in the repository |
| pytest, httpx (tests only) | `python3-pytest`, `python3-httpx` | MIT / BSD | development only |

The State design system (DSFR), the Marianne font and the bloc-marque of a
préfecture are **not** in this repository: their terms of use reserve them to
the State services. A place that is entitled to them uses a separate theme
that downloads them at install time (for the Préfecture de la Moselle:
<https://github.com/fbmguerin/februus-theme-moselle>); `deploy/theme-example/`
shows the structure.

EICAR (the antivirus test string) is generated at runtime, never stored.

# Font of the web UI

Files served by the station itself (`februus/web/static/`): a station has
no Internet access, nothing is loaded from another site.

The picture of Cerberus (rights not verified) was removed on 2026-10-05 before
the repository became public.

## Font (SIL Open Font License 1.1)

Downloaded on 2026-10-02 from https://github.com/google/fonts (folder
`ofl/`). The licence text is next to the font
(`februus/web/static/fonts/OFL-cinzeldecorative.txt`).

| File | Font | Author | Used for |
|---|---|---|---|
| `CinzelDecorative-Bold.ttf` | Cinzel Decorative | Natanael Gama | the name "Februus" only |

The other texts use DejaVu Sans, a font of Debian (package
`fonts-dejavu-core`), not stored in the repository.
