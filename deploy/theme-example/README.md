# Theme example

A theme gives a place its own look (logo, colors, fonts) without changing the
code of Februus. It is a folder with:

- `templates/`: files that replace the templates of `februus/web/templates/`
  with the same name (`base.html`, `_notice.html`, `idle.html`, ...);
- `static/`: files served as `/theme/...` (CSS, fonts, pictures). Nothing may
  be loaded from another site: a station has no Internet access.

Install it (as `root`, from the repository):

```
sudo deploy/install.sh --theme /path/to/the/theme-folder
```

The folder is copied to `/etc/februus/theme` (owned by `root`, read-only for
the service) and the service is restarted. To go back to the plain screens:
`sudo rm -r /etc/februus/theme && sudo systemctl restart februus`.

What a theme must keep (see the comment in `templates/base.html`): the
`<body>` classes and `data-key`, one `<main>` with the notice include and the
`content` block, the `<audio>` and the `live.js` script.

This example only adds a small mark in the top bar.
Do not put in this public repository anything that must not be reused by
everybody (a logo, an official mark): keep such a theme in its own, private
place.
