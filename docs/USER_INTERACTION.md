# User Interaction and Confirmation System

## Overview

AutoKaggle now includes a comprehensive user confirmation system that provides control and transparency over the automated workflow. This system ensures users are aware of and can control each major step in the competition pipeline.

## Features

### 1. **Confirmation Points**

The system requests user confirmation at the following key points:

- **Competition Data Fetching**: Before using crawl4ai to gather competition information
- **KSE Hypothesis Generation**: Before invoking Codex to generate experiment hypotheses
- **WAA Experiment Execution**: Before launching Worker AI Agents to run experiments
- **Performance Analysis**: Before invoking Codex to analyze experiment results
- **Score Submission**: Before submitting predictions to the Kaggle leaderboard

### 2. **Operation Modes**

#### Normal Mode (Default)
- Prompts for confirmation at each step
- Displays detailed information about what will happen
- Shows warnings about API usage and potential costs
- Allows users to cancel any operation

```bash
python main.py --config config/config.json
```

#### Automatic Mode
- Skips all confirmation prompts
- Runs the entire pipeline without interruption
- Useful for CI/CD or when running trusted workflows

```bash
python main.py --config config/config.json --skip-confirmations
# or use the short flag
python main.py --config config/config.json -y
```

#### Dry-Run Mode
- Shows what would be executed without actually running it
- Useful for testing configurations
- No Codex API calls are made

```bash
python main.py --config config/config.json --dry-run
```

#### Combined Mode
- Can combine automatic and dry-run modes
- Useful for automated testing

```bash
python main.py --config config/config.json -y --dry-run
```

## Confirmation Prompts

### Rich Terminal UI

The confirmation system uses the `rich` library to provide a beautiful terminal interface:

- **Color-coded messages**: Success (green), warnings (yellow), errors (red)
- **Formatted panels**: Clear visual separation of confirmation prompts
- **Progress indicators**: Visual feedback during operations
- **Detailed information**: Each prompt includes:
  - Action name
  - Description of what will happen
  - Additional details when relevant
  - Warnings about costs or time requirements

### Example Confirmation Prompt

```
┌─────────────────────────────────────────────────┐
│                 Action Required                  │
├─────────────────────────────────────────────────┤
│                                                   │
│  Generate Hypotheses (KSE)                      │
│                                                   │
│  Generate 5 experiment hypotheses for initial    │
│  iteration                                       │
│                                                   │
│  Details:                                        │
│  This will invoke Codex to create ML experiment  │
│  strategies based on competition analysis.       │
│                                                   │
│  ⚠️ Warning:                                     │
│  Codex API usage will be required (may incur     │
│  costs).                                         │
│                                                   │
└─────────────────────────────────────────────────┘
Do you want to proceed? [Y/n]:
```

## User Workflow

### Interactive Workflow

1. **Start AutoKaggle**
   ```bash
   python main.py --config config/titanic.json
   ```

2. **Review each step**
   - Read the confirmation prompt
   - Understand what will happen
   - Decide whether to proceed

3. **Make informed decisions**
   - Proceed with 'Y' or Enter (default)
   - Cancel with 'n'
   - Use Ctrl+C to abort completely

### Automated Workflow

1. **Configure once**
   - Set up your configuration file
   - Test with dry-run mode

2. **Run automatically**
   ```bash
   python main.py --config config/titanic.json -y
   ```

3. **Monitor logs**
   - All actions are logged
   - Review results after completion

## Configuration

### Command-Line Arguments

| Argument | Short | Default | Description |
|----------|-------|---------|-------------|
| `--config` | `-c` | `config/config.json` | Path to configuration file |
| `--skip-confirmations` | `-y` | `False` | Skip all confirmation prompts |
| `--dry-run` | | `False` | Run in dry-run mode (no actual executions) |

### Configuration File

The confirmation behavior can also be controlled via configuration:

```json
{
  "skip_confirmations": false,
  "dry_run": false,
  // ... other configuration
}
```

Note: Command-line arguments override configuration file settings.

## Benefits

### For Development
- **Safety**: Prevents accidental API calls during testing
- **Debugging**: Step through the pipeline interactively
- **Cost Control**: Review operations before incurring API costs

### For Production
- **Automation**: Run unattended with `--skip-confirmations`
- **CI/CD Integration**: Seamless integration with automated pipelines
- **Logging**: All decisions are logged for audit trails

### For Learning
- **Transparency**: Understand what each component does
- **Control**: Decide which experiments to run
- **Education**: Learn the AutoKaggle workflow step-by-step

## Error Handling

The system handles various scenarios gracefully:

- **User cancellation**: Cleanly stops the pipeline
- **Keyboard interrupt** (Ctrl+C): Immediate safe exit
- **Failed operations**: Clear error messages with recovery options

## Tips

1. **First-time users**: Run in normal mode to understand the workflow
2. **Testing configurations**: Use `--dry-run` to verify setup
3. **Production runs**: Use `-y` for unattended operation
4. **Debugging**: Use normal mode to step through problems
5. **Cost-conscious**: Review prompts to understand API usage

## Examples

### Example 1: Interactive Development
```bash
# Run with confirmations to control each step
python main.py --config config/house-prices.json
```

### Example 2: Automated Testing
```bash
# Test configuration without actual execution
python main.py --config config/test.json -y --dry-run
```

### Example 3: Production Pipeline
```bash
# Run fully automated for CI/CD
python main.py --config config/production.json -y
```

### Example 4: Selective Execution
```bash
# Run interactively and skip certain steps by answering 'n'
python main.py --config config/experiment.json
```

## Troubleshooting

### Issue: Prompts not appearing
- **Solution**: Ensure terminal supports interactive input
- **Alternative**: Use `--skip-confirmations` flag

### Issue: Accidental API calls
- **Prevention**: Always test with `--dry-run` first
- **Recovery**: Use Ctrl+C to abort immediately

### Issue: Want to automate specific parts
- **Solution**: Modify the code to add custom confirmation logic
- **Alternative**: Use the configuration file to control behavior

## Future Enhancements

Planned improvements to the confirmation system:

1. **Selective confirmations**: Skip only specific types of confirmations
2. **Batch confirmations**: Approve multiple actions at once
3. **Configuration profiles**: Save confirmation preferences
4. **Web UI**: Browser-based confirmation interface
5. **Notification system**: Send alerts for important decisions