# Brand assets

Home Assistant shows integration icons and logos only from its central
[brands repository](https://github.com/home-assistant/brands); a custom
integration cannot serve its own, which is why the device page shows a "logo not
available" placeholder until the assets below are merged there.

`brands/kestrel/` holds the Kestrel Instruments logo (© Nielsen-Kellerman Co.,
used to identify their products, taken from kestrelinstruments.com) prepared in
the sizes the brands repository requires:

| File | Size | Purpose |
|---|---|---|
| `icon.png` | 256×256 | Square icon: the Kestrel bird mark |
| `icon@2x.png` | 512×512 | High-DPI icon |
| `logo.png` | 500×166 | Full "Kestrel Instruments" logo |
| `logo@2x.png` | 1000×332 | High-DPI logo |

## Submitting to the brands repository

1. Fork https://github.com/home-assistant/brands and clone it.
2. Copy `brands/kestrel/*.png` into `custom_integrations/kestrel/` (create the
   directory; the name must equal the integration domain `kestrel`).
3. Commit and open a pull request titled "Add kestrel custom integration".
   The repository's checks validate the dimensions automatically.
4. Once merged, Home Assistant loads the images from
   `https://brands.home-assistant.io/_/kestrel/icon.png`; the frontend caches
   aggressively, so a hard refresh may be needed.
