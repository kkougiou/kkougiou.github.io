# Footer engraving

`assets/media/kk-engraving-*.webp` is the opening landscape photo
(`assets/media/hero-landscape.jpg`) redrawn as a line engraving.

To regenerate it (needs Python with `opencv-python`, `numpy`, `pillow`):

```bash
cd scripts/engraving
python sky_mask.py      # writes sky.npy (rough sky detection)
python ridge.py         # writes ridge.npy (sky line; the left slope is traced by hand)
python engrave.py 8     # 8 = line spacing in pixels; writes footer-engraving.webp
```

`tree.npy` marks the conifer so its foliage gets its own texture. The footer layout is in
`layouts/partials/components/footers/engraving.html` and the styles at the end of
`assets/scss/custom.scss`. To go back to the theme's plain footer, delete the line
`block: engraving` under `footer:` in `config/_default/params.yaml`.
