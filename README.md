# RAMSES UPISAS SETUP

- RAMSES INTERFACE should run on port 50000.
- In stop_existing_adaptation() function the port number 32836 should be set to the port number of "ramses-dashboard".
- Also keep in mind that stop_existing_adaptation() function stops the already existed adaptation mechanism of the RAMSES in order to try our new implemented baseline strategy.

## How to run Novel Strategy with Experiment Runner

```
cd experiment-runner
git submodule update --init --recursive
pip install -r requirements.txt
cd ..
sh run_novel.sh
```

## How to run Baseline Strategy with Experiment Runner

```
cd experiment-runner
git submodule update --init --recursive
pip install -r requirements.txt
cd ..
sh run_baseline.sh
```

## How to run Novel Strategy WITHOUT Experiment Runner manually

In a terminal, navigate to the parent folder of the project and issue:

```
python run_novel_ramses.py
```

## How to run Baseline Strategy WITHOUT Experiment Runner manually

In a terminal, navigate to the parent folder of the project and issue:

```
python run_baseline_ramses.py
```

## About Baseline Strategy

- In **Analyze phase**, it basically checks the monitored data first.
- If it detects instances with "FAILED" or "UNREACHABLE" status it appends it to failed_instances list.
- Finally it sets knowledge.analysis_data with failed_instances list.

- In **Plan phase**, it fetches the failed instance data from knowledge.analysis_data.
- Then for each failed instance it does the following operation:

```
adaptation_plan.append({
    "operation": "addInstances",
    "serviceImplementationName": service_id,
    "numberOfInstances": 1  # Start one new instance per service with failures
})
```

- Finally it sets the knowledge.plan_data with adaptation_plan

- In **Execute phase** it fetches the data from knowledge.plan_data first.
- Then for each adaptation action it sends a POST request for adaptation.

# UPISAS

Unified Python interface for self-adaptive system exemplars.

### Prerequisites

Tested with Python 3.9.12, should work with >=3.7.

### Installation

In a terminal, navigate to the parent folder of the project and issue:

```
pip install -r requirements.txt
```

### Run unit tests

In a terminal, navigate to the parent folder of the project and issue:

```
python -m UPISAS.tests.upisas.test_exemplar
python -m UPISAS.tests.upisas.test_strategy
python -m UPISAS.tests.swim.test_swim_interface
```

### Run

In a terminal, navigate to the parent folder of the project and issue:

```
python run.py
```

### Using experiment runner

**Please be advised**, experiment runner does not work on native Windows. Since UPISAS also uses docker, your Windows system should have the Windows Subsystem for Linux (WSL) installed already. You can then simply use Python within the WSL for both UPISAS and Experiment Runner (restart the installation above from scratch there, and then proceed with the below).

```
cd experiment-runner
git submodule update --init --recursive
pip install -r requirements.txt
cd ..
sh run.sh
```
