Creating and Editing the Model
==============================

The model can consist of up to six layers which represent physical parts of the network.

These layers are regular QGIS layers, and can be from any data source supported by QGIS, such as shapefiles, geopackages, a PostGIS database or memory layers.

There are three possible node layers (represented by point layers in QGIS):

* **Junctions**, which are points in the network where links join together and where water enters or leaves the network.

* **Reservoirs**, which are nodes that represent an infinite external source or sink of water to the network. They are used to model such things as lakes, rivers, groundwater aquifers, and tie-ins to other systems. Reservoirs can also serve as water quality source points.

* **Tanks**, which are nodes that represent a finite storage of water in the network. They are used to model water storage tanks, elevated tanks, and other types of water storage facilities.

There are also three possible link layers (represented by line layers in QGIS):

* **Pipes**, are links that convey water from one point in the network to another. EPANET assumes that all pipes are full at all times. Flow direction is from the end at higher hydraulic head (internal energy per weight of water) to that at lower head.

* **Valves**, which are used to control the flow of water in the network. They can be used to model pressure reducing valves, flow control valves, and other types of valves.

* **Pumps**, which are links that impart energy to a fluid thereby raising its
  hydraulic head. The principal input parameters are either it's pump curve
  or they can be represented as a constant energy device, one that supplies a
  constant amount of energy to the fluid for
  all combinations of flow and head.



Creating Layers
---------------

Each of the six types of physical object is represented by a normal layer in QGIS.
This can be any filetype: shapefile, geopackage, memory layer, etc.
Not all layers need to be present if they are not used.

You can use the 'new' button on the toolbar to create a set of layers with default properties.

.. image:: ../_static/new_button.png

Alternatively, for more control, you can use the 'Create Template Layers' processing tool.

It is also possible to use any layer - you do not have to use the layers created by the plugin.
Any layer with the appropriate geometry type (points for nodes and linestrings for links) and with the minimum necessary fields can be used.


Attributes
-----------
Attributes are based on the attributes within WNTR. Details of what they represent can be found in the WNTR and / or EPANET documentation.

Some attributes are required - these are marked with an asterisk (*). Others use default values from WNTR if not defined.

**Name** All layers can optionally use the attribute `name` to give a name to each item, which will be visible on the output layer. The name must be a string of less than 32 characters and with no spaces. If no name is given, it will be automatically generated.

**Patterns** All patterns are string fields. This can be left blank. Otherwise, it should be input as a series of numbers seperated by spaces:

``1  1.2 1.3 0.8``

Patterns will also accept a field of type list, where each item in the list is a number.

**Curves** Curves should be inputted with the following form, where each pair of numbers in brackets is an x, y point on the curve.

``(0, 10), (2, 5), (3.3, 7)``

**Geographical attributes** All geographical (`coordinates`, `vertices`) and network-related (`start_node_name` and `end_node_name`) WNTR attributes are not used. This is because they are calculated automatically based on the geometry of the features.


.. warning::
    The attributes must have the exact names listed below. However, when they are created by the plugin in QGIS, they will also be given 'alias' names, which will be more human-readable versions.
    These aliases will be most the most visible within the user interface.

    The alias names will also be translated if using the plugin in a different language, whilst the underlying attribute names will not be.

    The values of attributes may also be given aliases. For example, the `valve_type` attribute value 'PRV' can have the alias 'Pressure Reducing Valve'. The alias will be used in the user interface, but the underlying value will still be 'PRV'.


.. csv-table:: Possible Junction Attributes
    :file: ../_build/autogen-includes/junctions.csv
    :header-rows: 1

.. csv-table:: Possible Reservoir Attributes
    :file: ../_build/autogen-includes/reservoirs.csv
    :header-rows: 1

.. csv-table:: Possible Tank Attributes
    :file: ../_build/autogen-includes/tanks.csv
    :header-rows: 1

.. csv-table:: Possible Pipes Attributes
    :file: ../_build/autogen-includes/pipes.csv
    :header-rows: 1


.. csv-table:: Possible Pumps Attributes
    :file: ../_build/autogen-includes/pumps.csv
    :header-rows: 1

Pumps can be of two types: 'POWER' or 'HEAD'. The type of pump is determined by the `pump_type` attribute. These are not physically different types of pump, but rather different ways of representing the pump in the model.

Power pumps must have a `power` attribute, which is a float representing the power of the pump.

Head pumps must have a `pump_curve` attribute, which is a string representing the head curve of the pump in the form of a list of points, e.g. ``(0, 10), (2, 5), (3.3, 7)``.


.. csv-table:: Possible Valve Attributes
    :file: ../_build/autogen-includes/valves.csv
    :header-rows: 1

All valves must have a `valve_type` attribute. The options are:

* `PRV` - Pressure Reducing Valves limit the pressure at a point in the pipe network. They must have an `pressure_setting` attribute which represents that pressure.
* `PSV` - Pressure Sustaining Valves maintain a set pressure at a specific point in the pipe network. They must have an `pressure_setting` attribute which represents that pressure.
* `PBV` - Pressure Breaker Valves force a specified pressure loss to occur across the valve. They must have an `pressure_setting` attribute which represents that pressure loss.
* `FCV` - Flow Control Valves limit the flow to a specified amount. They must have a `flow_setting` attribute, which is a float representing the flow setpoint of the valve.
* `TCV` - Throttle Control Valves simulate a partially closed valve by adjusting the minor head loss coefficient of the valve. They must have a `throttle_setting` attribute, which represents the minor head loss coefficient of the valve.
* `GPV` - General Purpose Valves are used to represent a link where the user supplies a special flow - head loss relationship instead of following one of the standard hydraulic formulas. They can be used to model turbines, well draw-down or reduced-flow backflow prevention valves. They must have a `headloss_curve` attribute, which is a string representing the headloss curve of the valve in the form of a list of points, e.g. ``(0, 10), (2, 5), (3.3, 7)``.
