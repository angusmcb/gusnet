=================
PyQGIS API
=================

This is the fledgling documentation for the work-in-progress API. The API is likely to change at every release.

This API will allow you to use features in PyQGIS scripts and within the python console in QGIS.

Usage
======

First import gusnet and wntr. Note that this is not necessary from the QGIS console - they are already imported.

>>> import gusnet
>>> import wntr

We will use one of the example .inp files provided

>>> gusnet.examples
{'KY1': '...ky1.inp', 'KY10': '...ky10.inp', ...}

We can load the example file into QGIS

>>> layers = gusnet.to_qgis(gusnet.examples['KY10'], crs='EPSG:3089', units='LPS')
>>> layers
{'JUNCTIONS': <QgsVectorLayer: 'Junctions' (memory)>, 'RESERVOIRS': ..., 'TANKS': ..., 'PIPES': ..., 'PUMPS': ..., 'VALVES': ...}

The layers will now have been added to QGIS. You can make edits to them and create a :py:class:`~wntr.network.model.WaterNetworkModel` when done.

>>> wn = gusnet.from_qgis(layers, units='LPS', headloss='H-W')
>>> wn
<wntr.network.model.WaterNetworkModel object ...>

We can run a simulation and load the results back into QGIS.

>>> sim = wntr.sim.EpanetSimulator(wn)
>>> results = sim.run_sim()
>>> result_layers = gusnet.to_qgis(wn, results, crs='EPSG:3089', units='lps')
>>> result_layers
{'NODES': <QgsVectorLayer: 'Nodes' (memory)>, 'LINKS': <QgsVectorLayer: 'Links' (memory)>}

Reference
=========

.. automodule:: gusnet
	:members:
