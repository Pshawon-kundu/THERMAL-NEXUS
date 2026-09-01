# Software Roadmap

## Phase 1: Foundation and Synthetic Data

- Create project structure
- Define documentation and configuration files
- Implement synthetic thermal scenarios
- Generate CSV, metadata JSON, and plot outputs
- Add pytest coverage and code-quality checks

## Phase 2: Feature Engineering and Labeling

- Implement rolling features
- Define prediction labels for configured horizons
- Create train/validation/test splits
- Validate dataset quality

## Phase 3: Baselines

- Implement Mode A fixed sampling/transmission baseline
- Implement Mode B rule-based adaptive baseline
- Establish energy, packet, and excursion-warning metrics
- Audit dataset health and EDA plots
- Evaluate fixed-threshold and rule-based predictive baselines without training learned models

## Phase 4: TinyML Modeling

- Train lightweight predictive models
- Evaluate candidate models against baselines
- Export deployment-ready model artifacts
- Enforce training-only preprocessing, group-aware CV, validation-based selection, and locked test evaluation
- Keep Random Forest as a non-deployment reference unless later approved

## Phase 5: Protocol and Simulation

- Implement packet encoding and decoding
- Simulate wireless channel behavior
- Implement virtual reader ingestion
- Load selected model at runtime without retraining
- Run fixed, rule-based, and learned-model simulation modes
- Generate end-to-end software-simulation mode comparisons
- Clearly label estimated energy as software-estimated only

## Phase 6: Dashboard and KPI Analysis

- Build offline dashboard
- Add replay and comparison tools
- Summarize KPI results with clear simulation disclaimers
- Import end-to-end evidence into local SQLite
- Generate embedded preparation manifests, C99 source, golden vectors, parity
  evidence, and resource estimates without physical firmware

## Phase 7: Hardware Integration

- Integrate TMP117 and STM32U585 firmware
- Validate XBee-PRO 900HP communication
- Compare physical measurements with simulation assumptions
