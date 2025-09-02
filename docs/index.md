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
  margin-top: 2.5rem;
  margin-bottom: 2rem;
}

.big-section {
  min-height: 80vh
}
.bd-main .bd-content .bd-article-container {
  max-width: 100%;  /* default is 60em */
}
.key-features img {
  max-width: 20vw
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

```{image} _static/screenshot.jpg
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


::::::{grid} 1 1 2 2
:gutter: 5
:margin: 5 5 0 0
:class-container: key-features sd-fs-5


:::::{grid-item}
:child-direction: row
:class: sd-align-minor-center

```{image} _static/QGIS_logo_minimal.svg
:class: sd-mr-4 dark-light
:width: 150px
```

:::{div}
**Fully Integrated with QGIS**<br/>
Build models that exist in real places, combining with other GIS data sources.
:::

:::::

:::::{grid-item}
:child-direction: row
:class: sd-align-minor-center

```{image} _static/wntr-logo.png
:class: sd-mr-4 dark-light
:width: 150px
```

:::{div}
**EPANET Modelling**<br/>
Uses WNTR and EPANET for reliable, accurate results and interoperability.
:::

:::::

:::::{grid-item}
:child-direction: row
:class: sd-align-minor-center

```{image} _static/code.svg
:class: sd-mr-4 only-light
:width: 150px
```

```{image} _static/code-white.png
:class: sd-mr-4 only-dark
:width: 150px
```

:::{div}
**Free and Open Source**<br/>
No cost, no licensing problems, no limit on the number of pipes.
:::

:::::

:::::{grid-item}
:child-direction: row
:class: sd-align-minor-center

```{image} _static/noun-987.svg
:class: sd-mr-4 only-light
:width: 150px
```

```{image} _static/noun-987-white.png
:class: sd-mr-4 only-dark
:width: 150px
```

:::{div}
**User Friendly**<br/>
Translated, easy to learn, flexible, fully documented.
:::

:::::

::::::



## Explore More


```{toctree}
:maxdepth: 2

user-guide/index
```
