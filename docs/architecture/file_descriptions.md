
1. main.py

Role: Entry Point & Initialization. This script is the starting point for the entire simulation.

Expected Behavior:

Reads the config.json file to load system-wide settings.
Sets up the global logger using configurations from the config file.
Ensures necessary directories (logs/, experiments/, etc.) exist.
Performs a basic check to ensure the execution directory is a Git repository.
Instantiates the MasterControllerDecisionUnit (MCDU).
Calls the main execution loop (run_main_loop) of the MCDU to start the simulation.
Handles top-level exceptions and logs the final status (success or critical error).

2. config.json (Configuration File)

Role: System Configuration Storage. This file holds all the parameters that control the simulation's behavior.

Expected Behavior:
Contains key-value pairs for settings like the target Kaggle competition name (for simulation), maximum iterations, number of Worker Agents per iteration, stopping conditions (score threshold, iterations without improvement), base directory for experiments, log file path, and log level.
It is read by main.py at startup and passed to various components.

3. data_models.py

Role: Data Structure Definition. This module defines the structure of data objects passed between different components using Python's dataclasses.

Expected Behavior:
Defines classes like CompetitionInfo, ExperimentHypothesis, ExperimentResult, and AnalysisResult.
Ensures consistent data representation throughout the system, improving code readability and maintainability.
Specifies expected data types for attributes (e.g., str, int, Optional[float], List[str], Dict[str, Any]).

4. utils/logger.py

Role: Logging Configuration Utility. Provides a centralized function to set up the application's logger.

Expected Behavior:
Configures a logger instance (named 'AutoKaggle') to output logs to both a file (with detailed formatting) and the console (with simpler formatting).
Allows setting the logging level based on the configuration.
Used by main.py to initialize logging and potentially by other modules if needed (though BaseComponent handles logger retrieval for components).

5. utils/file_utils.py

Role: File System Interaction Utilities. Contains helper functions for common file and directory operations.

Expected Behavior:
Provides functions to ensure directories exist (ensure_dir), read/write JSON files (read_json, write_json), read/write Markdown files (read_markdown, write_markdown), copy/move files (copy_file, move_file), and remove directories (remove_dir).
Includes basic logging for file operations and error handling.
Used by various components (e.g., RAD, KSE, EO) to interact with the file system reliably.

6. components/base_component.py

Role: Base Class for Components (Optional but Recommended). Provides common initialization logic for all system components.

Expected Behavior:
Initializes components with the shared configuration dictionary.
Sets up a dedicated logger instance for each component subclass (e.g., AutoKaggle.KIM, AutoKaggle.KSE).
Optionally provides helper methods for consistent logging of method start/end/error events (_log_start, _log_end, _log_error).

7. components/kim.py (Kaggle Interface Manager)

Role: Interface to Kaggle Platform. Responsible for all direct interactions with Kaggle (simulated in this version).

Expected Behavior:
(Simulation): Generates dummy CompetitionInfo (name, metric, description, file list). Creates dummy data files in a designated directory (experiments/kaggle_data/) to simulate downloading. Simulates the submission process by logging a message.
(Real Implementation): Would use the official kaggle library to authenticate, fetch real competition details, download actual data files, and submit prediction files via the Kaggle API.

8. components/kse.py (Knowledge & Strategy Engine)

Role: Strategy Brain. Responsible for analyzing information and generating experiment hypotheses.

Expected Behavior:
Receives CompetitionInfo from KIM (via MCDU).
(Simulation): Generates initial hypotheses randomly selecting from predefined strategies (SimpleGBM, BasicNN, etc.) and generating dummy parameters. For subsequent iterations, it receives simulated AnalysisResult and ExperimentResult lists and might slightly bias strategy selection (e.g., prioritizing "recommended" strategies from the dummy analysis) before generating new hypotheses with dummy parameters.
Generates task instruction Markdown files (task_N.md) for each hypothesis, detailing the (simulated) work the WAA should perform. These files are saved in experiments/hypotheses/.
(Real Implementation): Would involve more sophisticated logic, potentially using NLP to parse real competition descriptions and discussions, analyzing past experiment results more deeply to guide parameter tuning (e.g., Bayesian optimization), and employing more complex strategy selection rules.

9. components/eo.py (Experiment Orchestrator)

Role: Experiment Execution Manager. Manages the lifecycle of experiments and Worker AI Agents (WAAs).

Expected Behavior:
Receives a list of ExperimentHypothesis from KSE (via MCDU).
Uses the GitPython library to create a unique Git worktree (experiments/worktrees/exp_id/) for each hypothesis, branching off the main repository.
Starts a separate Python process for each experiment using multiprocessing, running the wca_simulator.py script within its designated worktree and passing necessary arguments (worktree path, task markdown path, experiment ID).
Keeps track of active WAA simulator processes.
Periodically checks for the completion of WAA processes (by looking for a DONE_exp_id file within the worktree).
Cleans up completed worktrees (removes the directory and prunes Git worktree information).

10. components/wca_simulator.py (Worker Agent Simulator)

Role: Worker Agent Simulation. Simulates the behavior of an AI agent executing a single experiment task. This runs as an independent process.

Expected Behavior:
Receives arguments (worktree path, task markdown path, experiment ID) from the EO.
Sets up its own local logger, writing logs to a file within its worktree (waa_exp_id.log).
Reads the task markdown file (simulating understanding instructions).
Simulates work by pausing for a random duration (time.sleep).
Generates a random dummy score and simulates potential failures (with a small probability).
Creates dummy output files within its worktree (e.g., result_exp_id.json containing the score, submission_exp_id.csv, model_exp_id.pkl).
Creates a DONE_exp_id file upon completion (writing "SUCCESS" or "FAILURE" inside) to signal the EO. If an error occurs, it writes error details to ERROR_exp_id.log and sets status to "FAILURE".

11. components/rad.py (Result Aggregator & Database)

Role: Result Collector and Storage. Gathers results from completed experiments and stores them persistently (simulated as files).

Expected Behavior:
Receives notification (via MCDU/EO) about a completed experiment ID and its worktree path.
Reads the status from the DONE_exp_id file.
Reads the generated score from result_exp_id.json.
Copies relevant output files (logs, submission, model) from the completed worktree into a centralized results directory (experiments/results/exp_id/).
Creates an ExperimentResult dataclass instance.
(Simulation Persistence): Stores all collected ExperimentResult objects in a central JSON file (experiments/results/results_manifest.json) acting as a simple database. It loads this manifest on startup and saves it after collecting each result.
Provides methods to retrieve all results or results for a specific iteration. Updates result metadata (like iteration number, strategy) after collection based on hypothesis info provided by MCDU.

12. components/pa.py (Performance Analyzer)

Role: Result Analysis Engine. Analyzes aggregated experiment results to provide insights.

Expected Behavior:
Receives a list of ExperimentResult for the current iteration from RAD (via MCDU).
(Simulation): Performs basic analysis: calculates success/failure rates, finds the best score in the iteration, sorts results. Generates a simple list of "recommended" strategies (e.g., successful ones). Compares the current iteration's best score to the overall best score (tracked by MCDU) to determine an "improvement trend" (simulated).
Generates a summary report in Markdown format (analysis_iter_N.md) and saves it to experiments/analysis/.
Returns an AnalysisResult dataclass containing the summary, best score/ID for the iteration, trend, and recommendations.
(Real Implementation): Would involve much more sophisticated statistical analysis, visualization generation, comparison across iterations, identification of impactful features/parameters, and potentially using ML models to predict promising future experiments.

13. components/mcdu.py (Master Controller & Decision Unit)

Role: Central Orchestrator and Decision Maker. Controls the overall workflow and makes high-level decisions.

Expected Behavior:
Initializes all other components.
Runs the main control loop:
Calls KIM to get competition info and download data (simulated).
In each iteration:
Calls KSE to generate hypotheses.
Calls EO to launch experiments (start WAA processes).
Waits for EO to report completed experiments.
Instructs RAD to collect results for completed experiments.
Updates RAD results with metadata from KSE's hypotheses.
Calls PA to analyze the iteration's results.
Updates its internal state (overall best score, iterations without improvement).
Determines whether to stop the loop based on configured conditions (max iterations, score threshold, no improvement).
If stopping, identifies the overall best result and simulates final submission by calling KIM.
Coordinates the flow of data and control signals between all other components.
