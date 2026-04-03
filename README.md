<img src="https://raw.githubusercontent.com/usepa/wntr/main/documentation/_static/logo.jpg" width="375"> <img src="https://raw.githubusercontent.com/qgis/QGIS/master/images/README-md/main_logo.png" width="300">


![tests](https://github.com/angusmcb/gusnet/workflows/Tests/badge.svg)
[![codecov.io](https://codecov.io/github/angusmcb/gusnet/coverage.svg?branch=main)](https://codecov.io/github/angusmcb/gusnet?branch=main)
![release](https://github.com/angusmcb/gusnet/workflows/Release/badge.svg)

[![GPLv2 license](https://img.shields.io/badge/License-GPLv2-blue.svg)](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)

<!-- sphinx content start -->

# Gusnet Piped Water Network Modelling

This QGIS plugin integrates the US EPA's [Water Network Tools for Resilience (WNTR)](https://usepa.github.io/WNTR/) with [QGIS](https://qgis.org/).

A plugin for doing all aspects of piped water networks analysis directly within QGIS. This includes the creation of the model, the simulation and the visualisation of results.

It is compatible with and import/exports to EPANET. It uses the EPANET solver by default.

Compared to other QGIS water network modelling plugins, this plugin aims to be:
- **Easy to use.** Accessible for those who know how to use QGIS. Well documented, good defaults, clear functionality.
- **Integrate the power of QGIS and WNTR.** It aims to complement rather than replace features already within QGIS. Data can be manipulated with the standard QGIS tools, processing algorithms, and plugins.
- **Robust.** Limited, well tested features (more than 500 tests).
- **Flexible.** Not choosy about how you do things.
- **Automatable / programmable.** Tools can be used from the toolbar, in the QGIS 'model builder' or from  PyQGIS
- **Multi-lingual** English, French, Spanish, Italian, Dutch, Arabic...


Feedback on this plugin would be very welcome.

<!-- sphinx content end -->

## Installation

Install the plugin in QGIS in the normal way (see the [QGIS Manual](https://docs.qgis.org/latest/en/docs/training_manual/qgis_plugins/fetching_plugins.html) if necessary). QGIS 3.34 or greater is required.

If WNTR is not already installed in the python environment, it will be installed within the plugin directory when first running the tools.

WNTR itself has some python dependencies. A warning will appear when running any of the algorithms from the 'processing toolbox' if there are missing dependencies.
* On *Windows* all dependencies are already included within QGIS.
* For *Linux / Mac* you will need to ensure that the following python packages are installed: Numpy, Scipy, Pandas, NetworkX,  Matplotlib and Geopandas. Exactly how to do this depends on your system and how you have installed QGIS.

## Translations (gettext / pybabel)

Translations are managed with gettext catalogs (`.po` / `.mo`) using `pybabel`. Source strings are extracted from all Python files under `gusnet/` and use the existing `tr(...)` wrapper.

### Prerequisites

Install Babel in your active environment:

```bash
pip install Babel
```

### Workflow

Run all translation steps:

```bash
python build_translations.py all
```

Or run individual steps:

```bash
# Extract template catalog
python build_translations.py extract

# Initialize new locale catalogs (only if missing)
python build_translations.py init --locales fr es de it pt nl ar en

# Update existing locale catalogs from the latest template
python build_translations.py update --locales fr es de it pt nl ar en

# Compile .po files to .mo files
python build_translations.py compile
```

Catalog locations:

* Template: `gusnet/resources/i18n/messages.pot`
* Locales: `gusnet/resources/i18n/locales/<locale>/LC_MESSAGES/gusnet.po`
* Compiled: `gusnet/resources/i18n/locales/<locale>/LC_MESSAGES/gusnet.mo`

## Usage

### Key Principles

WNTR will have created three new processing algorithms. If you can't see the processing toolbox activate it in the menu View -> Panels -> Processing Toolbox.

![image](docs/_static/screenshot_processing_tools.png)

Whilst the plugin is very flexible in how it's used, the key principles are the following four steps:

1. **Layer Creation** Layers can either be created using the 'Create Template Layers' processing algorithm, or imported from EPANET files using the tools provided in the processing toolbox (or you can create them manually). If you are not sure where to start, type 'Net3.inp' into the 'Import from EPANET .inp file' algorithm. All of the layers are optional - only create what you need.
	- Junctions
	- Reservoirs
	- Tanks
	- Pipes
	- Pumps
	- Valves

![input image](docs/_static/input_screenshot.png)


2. **Layer Editing.** The layers are normal QGIS layers and can be edited / modified / processed / styled / automated in the same ways as any other QGIS layer. In particular:
   	- *Digitize* from any of the enormous range of data that QGIS can handle.
	- *Snapping tools* can be used when drawing the network to make sure that nodes and links connect.
	- *Pipe lengths* can be calculated automatically (this expression is added by default to new pipe layers).
	- *Elevations* can be added to nodes from other sources using either expressions or processing tools..
	- *External data sources* or any other layers can be used as background maps or data sources for drawing the network.

4. **Running the simulation.** The plugin will load your nodes, links, patterns, curves and options into WNTR and run the model It will then process the output into a new link and node layer containing all calculated results. Configure your analysis options to exploit the full power or WNTR and EPANET.

5. **Viewing the results.** Use all the power of QGIS to view and analyse your results.
   - Use all of QGIS's styling functions to look at all the results in nodes and links - pressure, flow, head, etc.
   - Use QGIS's temporal manager to view how your results change over time.

![input image](docs/_static/output_screenshot.png)

## Limitations
The plugin is currently marked as experimental. Some features which exist in WNTR / EPANET  are not yet implemented:
* Water quality analysis
* Controls
* Multiple demands per node.
* Patterns on valves

In addition, shapefile support is limited (due to a limitation of attribute length to 254 characters)

## License
This plugin is distributed under the terms of the [GNU General Public License, version 2](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html) license.


See [LICENSE](LICENSE) for more information.
