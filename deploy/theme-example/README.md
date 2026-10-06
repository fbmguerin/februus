# Theme example

A theme gives a place its own look (logo, colors, fonts) without changing the
code of Februus. It is a folder with:

- `templates/`: files that replace the templates of `februus/web/templates/`
  with the same name (`base.html`, `_notice.html`, `idle.html`, ...);
- `static/`: files served as `/theme/...` (CSS, fonts, pictures). Nothing may
  be loaded from another site: a station has no Internet access.

Install it (as root, `su -`, from the repository):

```
deploy/install.sh --theme /path/to/the/theme-folder
```

Only its `templates/` and `static/` folders are copied to `/etc/februus/theme`
(owned by `root`, read-only for the service) and the service is restarted. To go back to the plain screens:
`rm -r /etc/februus/theme && systemctl restart februus` (as root).

What a theme must keep (see the comment in `templates/base.html`): the
`<body>` classes and `data-key`, one `<main>` with the notice include and the
`content` block, the `<audio>` and the `live.js` script.

This example only adds a small mark in the top bar.
Do not put in this repository anything that must not be reused by everybody
(a logo, an official mark): keep such a theme in its own repository, and do
not redistribute what you are not allowed to (see the example of the
Préfecture de la Moselle theme, which downloads the State design system at
install time instead of storing it).
