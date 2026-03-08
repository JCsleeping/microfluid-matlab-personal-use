# Contributing

Thank you for considering contributing to the DNAPL Microfluidic Image Analysis Toolbox!

## How to Contribute

### Reporting Bugs

1. Check [existing issues](https://github.com/JCsleeping/microfluid/issues) to avoid duplicates
2. Open a new issue with:
   - MATLAB version and OS
   - Steps to reproduce
   - Expected vs. actual behavior
   - Error messages (full stack trace)

### Suggesting Features

Open an issue with the `enhancement` label describing:

- The problem you're trying to solve
- Your proposed solution
- Alternative approaches considered

### Submitting Code

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Run the test suite: `runtests('tests')`
5. Commit with a descriptive message
6. Push and open a Pull Request

## Code Style

### MATLAB Conventions

- **Function files**: One public function per file, lowercase with underscores (`segment_DNAPL.m`)
- **Variables**: `snake_case` for variables, `UPPER_CASE` for constants
- **Comments**: Use `%` for inline, `%%` for section headers
- **Function headers**: Include help block with signature, description, and I/O documentation

```matlab
function [output1, output2] = my_function(input1, input2, config)
% MY_FUNCTION  Brief one-line description.
%
%   [output1, output2] = my_function(input1, input2, config)
%
%   Inputs:
%       input1 - Description
%       input2 - Description
%       config - Pipeline configuration struct
%
%   Outputs:
%       output1 - Description
%       output2 - Description
```

### Project Structure

- `preprocessing/` — Image correction before segmentation
- `segmentation/` — Core DNAPL detection algorithms
- `analysis/` — Quantitative metrics extraction
- `visualization/` — Figure generation
- `utilities/` — Helper functions
- `tests/` — Test scripts
- `docs/` — Documentation (Chinese)

## Testing

Run all tests:

```matlab
results = runtests('tests');
disp(results);
```

When adding new functions, please add corresponding tests in `tests/`.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
