---
myst:
  html_meta:
    "description lang=en": |
        Documentation of the Gusnet plugin for QGIS
html_theme.sidebar_secondary.remove: true
sd_hide_title: true
---
<style>
h2 {
  text-align: center;
  margin-top: 5rem;
  margin-bottom: 2rem;
  font-size: 3rem;
}

.big-section {
  min-height: 80vh
}
.bd-main .bd-content .bd-article-container {
  max-width: 100%;  /* default is 60em */
}

.bd-container::before {
  content: "";
  position: absolute;
  top: 0; left: 50%; right: 0; bottom: 0;
  background: url('_static/network.png') no-repeat right top;
  background-size: contain;
  opacity: 0.3;
  pointer-events: none;
  z-index: -1
}

.full-width {
  width: 100%;
  height: fit-content;
  max-height:8rem;
}

.no-p-margin p {
  margin-bottom: 0
}

</style>

# Gusnet Water Network Modeller


::::{grid} 1 1 2 2
:reverse:
:class-row: big-section

:::{grid-item}
:margin: auto
:padding: 4
:child-direction: row
:child-align: center

```{image} _static/nice-output5.jpg
:width: 500px
:class: sd-rounded-3 sd-shadow-sm
```
:::

:::{grid-item}
:margin: auto
:class: sd-fs-5


  <h1 style="font-size: 80px; font-weight: bold;margin: 0">Gusnet</h1>
  <div style="font-weight: bold; margin-top: 0;" class="h3">Water Network Modeller</div>

  Gusnet is a QGIS plugin for designing, editing, simulating, and visualizing water distribution networks using EPANET’s trusted modeling engine.

  Create accurate hydraulic models in real-world locations using geographic data.

:::

::::



## Key Features


::::::{grid} 1 1 5 4
:gutter: 2 5 5 5
:margin: 5 5 0 0
:class-container: sd-fs-5 no-p-margin
:class-row: sd-align-major-center

:::::{grid-item}
:columns: 4 4 4 2
:margin: 5 0 0 0
```{image} _static/QGIS_logo_minimal.svg
:class: dark-light no-scaled-link full-width
```
:::::

:::::{grid-item}
:columns: 12 8 8 4
**Fully Integrated with QGIS**

Build models that exist in real places, combining with other GIS data sources.
:::::

:::::{grid-item}
:columns: 4 4 4 2
:margin: 5 0 0 0
```{image} _static/wntr-logo.svg
:class: dark-light no-scaled-link full-width
```
:::::

:::::{grid-item}
:columns: 12 8 8 4
**EPANET Modelling**

Uses WNTR and EPANET for reliable, accurate results and interoperability.
:::::

:::::{grid-item}
:columns: 4 4 4 2
:margin: 5 0 0 0
<i class="fa-solid fa-code full-width"></i>
:::::

:::::{grid-item}
:columns: 12 8 8 4
**Free and Open Source**

No cost, no licensing problems, no limit on the number of pipes.
:::::

:::::{grid-item}
:columns: 4 4 4 2
:margin: 5 0 0 0
<i class="fa-regular fa-smile full-width"></i>
:::::

:::::{grid-item}
:columns: 12 8 8 4

**User Friendly**

Translated, easy to learn, flexible, fully documented.
:::::

::::::



## Explore More


```{toctree}
:maxdepth: 2

user-guide/index

```
