# ML Problem Definition

## Primary Objective

Predict whether temperature will cross a configurable upper or lower safety limit within a configurable future prediction horizon.

Initial prediction horizons:

- 5 minutes
- 10 minutes
- 15 minutes

## Model Outputs

Future models may output:

- Excursion probability
- Optional predicted future temperature
- Temperature state: `STABLE`, `TRANSITION`, or `EXCURSION_RISK`
- Recommended sampling policy
- Recommended transmission policy

## Candidate Future Features

- Current temperature
- Temperature difference
- Temperature slope
- Temperature acceleration
- Rolling mean
- Rolling standard deviation
- Rolling minimum
- Rolling maximum
- Rolling range
- Distance from upper limit
- Distance from lower limit

## Scope Boundary

This repository currently implements a software-only foundation and synthetic thermal-data generator. No machine-learning model is trained in this phase.

Final competition results require real hardware measurements from the physical system. Synthetic and simulated outputs must not be reported as real hardware or competition results.

