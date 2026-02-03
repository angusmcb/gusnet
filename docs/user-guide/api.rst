=================
PyQGIS API
=================

The API lets you import and export to and from the WNTR python package.

You will need to have WNTR installed in the same python environment as QGIS.

This is the fledgling documentation for the work-in-progress API. The API is likely to change at every release.

Usage
======

Once installe, the easiest way to use the api is within the QGIS python console.

First import gusnet and wntr. Note that this is not necessary from the QGIS console - they are already imported.

>>> import gusnet
>>> import wntr

We will use one of the example .inp files provided

>>> gusnet.examples
{'KY1': '...ky1.inp', 'KY10': '...ky10.inp', ...}

We can load the example file into QGIS

>>> layers = gusnet.from_inp(gusnet.examples['KY10'], crs='EPSG:3089')
>>> layers
{'JUNCTIONS': <QgsVectorLayer: 'Junctions' (memory)>, 'RESERVOIRS': ..., 'TANKS': ..., 'PIPES': ..., 'PUMPS': ..., 'VALVES': ...}

The layers will now have been added to QGIS. You can make edits to them and create a :py:class:`~wntr.network.model.WaterNetworkModel` when done.

>>> wn = gusnet.to_wntr(layers, units='GPM', headloss_formula='H-W')
>>> wn
<wntr.network.model.WaterNetworkModel object ...>

We can run a simulation and load the results back into QGIS.

>>> sim = wntr.sim.EpanetSimulator(wn)
>>> results = sim.run_sim()
>>> result_layers = gusnet.from_wntr(wn, results, crs='EPSG:3089')
>>> result_layers
{'NODES': <QgsVectorLayer: 'Nodes' (memory)>, 'LINKS': <QgsVectorLayer: 'Links' (memory)>}

Reference
=========

.. automodule:: gusnet
	:members:
