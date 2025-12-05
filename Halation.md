# Physically-Inspired Halation (Overview + Controls)

## What is halation?

Halation is the red-to-orange halo seen around intense highlights on motion-picture and still film. Light penetrates the emulsion stack (blue → green → red), reflects off the base/backing when the anti-halation (AH) layer is weak or absent, then travels back through the layers. The reflected path excites red first, and at higher intensities leaks into green; the combined emission appears red to orange.

Key drivers:

* Highlight intensity and area
* Emulsion density and AH effectiveness
* Optical spread within/under the emulsion (radius and falloff)
* Channel bias (red dominant, green secondary)

## Simulation approach used here

This app implements a **physically-inspired** approximation that is fast and preview-friendly:

1. **Highlight isolation** – luminance threshold selects only the brightest cores.
2. **Energy spread** – gaussian blur spreads that energy outward; optional multi-pass simulates softer, near-exponential falloff.
3. **Channel bias** – controlled tinting prioritises red, with optional green contribution for orange roll-off.
4. **Screen compositing** – add back over the base via screen blend (preserves highlight shape).
5. **Order-aware look transforms** – optional 3D LUT before or after halation with adjustable strength and interpolation.
6. **Pre/Post grading** – gentle linear adjustments to guide the look into or out of a LUT.

This is not a literal film-transport model; it’s designed to be faithful in feel while remaining real-time and portable across GPUs/CPUs via FFmpeg.

---

## Controls (and how they map to the physics)

**Halation**

* **Threshold (min/max)** – how bright pixels must be to contribute. Higher threshold ≈ stronger AH layer / denser stock.
* **Radius (σ min/max)** – gaussian blur sigma; larger values ≈ deeper spread through layers/backing.
* **Opacity (min/max)** – mix of the halo with the base. Higher values ≈ more visible halation.
* **Tint** – `neutral`, `warm` (red bias), `cool` (slight cyan cut). Use warm for classic film halation; neutral for grayscale testing.

**LUT**

* **3D LUT** – select any `.cube` placed in `luts/`.
* **Strength (0–1)** – blends LUT output with the un-LUTed signal for subtlety or full application.
* **Interpolation** – `nearest`, `trilinear`, `tetrahedral` (recommended).
* **Order** – `pre` applies LUT before halation (shifts what “counts” as a highlight); `post` applies LUT after halation (grades the finished glow).

**Pre/Post Grade**

* **Pre**: brightness / contrast / gamma / saturation – nudge exposure and contrast into a favourable zone for thresholding.
* **Post**: brightness / contrast / gamma / saturation – small trims after halation/LUT to land the final look.

**Variant count**

* Generates a sweep across the min→max ranges (threshold, radius, opacity) to compare multiple looks at once.

---

## Practical recipes

**Classic subtle 35mm**

* Threshold 235–245, Radius σ 6–10, Opacity 0.15–0.25, Tint warm.
* LUT order: post; LUT strength 0.6–0.8 (e.g., Kodak print LUT).
* Pre: contrast 1.05; Post: gamma 0.95.

**Cinestill-style strong halation**

* Threshold 220–232, Radius σ 10–16, Opacity 0.25–0.35, Tint warm.
* Pre: brightness +0.02 to encourage highlight catch.
* Optional: Post saturation +0.05.

**Ultra-clean digital with controlled glow**

* Threshold 240–250, Radius σ 4–8, Opacity 0.10–0.18, Tint neutral.
* LUT order: pre (scene-referred grading first), strength 0.4–0.6.

---

## Under the hood (FFmpeg filter sketch)

The app builds a graph like:

```
[0:v]format=yuv444p,split=2[base][hi];
[hi]lut=y='if(gte(val,THR),val,0)',gblur=sigma=SIGMA[soft];
[soft]COLOR_BIAS[hal];
[base][hal]blend=all_mode=screen:all_opacity=OPACITY[hv];

# Optional LUT before or after halation with strength:
# Pre:  [hv] is replaced with LUT(pre) then halation runs
# Post: [hv] -> lut3d -> blend with original by strength
```

Where `COLOR_BIAS` is:

* Neutral: `hue=s=0`
* Warm: `colorchannelmixer=rr=1.05:gg=1.00:bb=0.98`
* Cool: `colorchannelmixer=rr=0.99:gg=1.00:bb=1.04`

For gentler, near-exponential falloff, the app may internally stack smaller blurs (e.g., σ 4 then σ 8) and mix them with decreasing weights before the screen pass.

---

## Workflow guidance

1. Start with a modest **threshold** (≈235) and **radius** (σ 8–10).
2. Adjust **opacity** until halos are visible but not washing out detail.
3. Pick **tint warm** for red-orange signature, then refine **LUT order**:

   * **Post** if the LUT is creative finishing.
   * **Pre** if the LUT defines scene response and highlight placement.
4. Use **pre-grade** to push highlights into the selection (small brightness/contrast tweaks), and **post-grade** for final polish.
5. Generate multiple **variants**; pick the one that best balances extension of the highlight core with a soft orange falloff.

---

## Notes on “physical accuracy”

* True film halation depends on stock, thickness, rem-jet/AH layer, exposure level, and optics.
* This implementation prioritises highlight-driven spread with red/green bias and soft, layered falloff using portable filters.
* For scene-referred work, feed linear/scene-like footage, apply halation, then tone-map; for display-referred workflows, use **pre** LUT order to adjust the highlight population before halation.

---

## Example full-video export (keep audio)

```bash
ffmpeg -i in.mp4 \
-filter_complex "
[0:v]format=yuv444p,split=2[b][h];
[h]lut=y='if(gte(val,235),val,0)',gblur=sigma=10[s];
[s]colorchannelmixer=rr=1.05:gg=1.00:bb=0.98[hal];
[b][hal]blend=all_mode=screen:all_opacity=0.22[v]
" \
-map "[v]" -map "0:a?" -c:v libx264 -crf 18 -preset slow -c:a copy out_halation.mp4
```

To include a LUT after halation:

```bash
ffmpeg -i in.mp4 \
-filter_complex "
[0:v]format=yuv444p,split=2[b][h];
[h]lut=y='if(gte(val,235),val,0)',gblur=sigma=10[s];
[s]colorchannelmixer=rr=1.05:gg=1.00:bb=0.98[hal];
[b][hal]blend=all_mode=screen:all_opacity=0.22[hv];
[hv]lut3d=file='luts/Kodak_2383.cube':interp=tetrahedral[v]
" \
-map "[v]" -map "0:a?" -c:v libx264 -crf 18 -preset slow -c:a copy out_halation_lut.mp4
```

---

## Where this lives in the app

* UI: **Halation settings**, **LUT settings**, **Pre/Post grading** panels in `templates/index.html`.
* Server: filter assembly happens in `app.py` (`build_filter(...)`), with LUT order/strength and grading applied as configured.
* LUTs: place `.cube` files in `luts/`; they are listed at runtime and selectable in the UI.
