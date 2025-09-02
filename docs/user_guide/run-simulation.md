# Running the Simulation

By pressing the lightning bolt icon in the toolbar, Gusnet will run your current model using the EPANET engine.

## Configuring Simulation Options

Certain analysis options can be configured before running the simulation. Notably:

- **Duration**:
  Choose between a single time step (snapshot) or a time series simulation.
  - *Single time*: The simulation will compute results for one specified time.
  - *Time series*: The simulation will compute results for each time step over the specified duration.

- **Headloss Equation**:
  Select the formula used to calculate headloss in pipes. The options are:
  - Hazen-Williams
  - Darcy-Weisbach
  - Chezy-Manning

- **Unit Set**:
  Choose the set of units to use for input and output (e.g., SI or US customary units).

To access these options, open the simulation settings dialog (usually accessible via the toolbar or menu). Adjust the settings as needed for your analysis.

## Running the Simulation

Click the lightning bolt icon to start the simulation. The simulation should run almost instantly.



## Troubleshooting

If the simulation fails, you will get an explanatory error message.

If it isn't clear, please raise an issue on the github repository explaining the problem.
