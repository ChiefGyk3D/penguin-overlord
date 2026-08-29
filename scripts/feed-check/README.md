# Test Scripts

This directory contains test scripts for various components of Penguin Overlord.

## Test Files

### `test_secrets.py`
Tests the secrets management system (Doppler, AWS, Vault integration).

```bash
python tests/test_secrets.py
```

### `test_comic_command.py`
Tests the comic posting functionality.

```bash
python tests/test_comic_command.py
```

### `test_fetcher.py`
Tests the optimized news fetcher with ETag caching.

```bash
python tests/test_fetcher.py
```

### `test_us_legislation.py`
Tests US legislation RSS feed accessibility.

```bash
python tests/test_us_legislation.py
```

### `test_propagation_standalone.py` ⭐ **NEW**
**Standalone test** for radiohead.py physics-based propagation engine.
No Discord or dependencies required - tests all propagation calculations locally!

```bash
# Default test (SFI=145, K=2, current hour)
python3 tests/test_propagation_standalone.py

# Custom parameters
python3 tests/test_propagation_standalone.py --sfi 150 --k 3 --hour 12

# Solar minimum
python3 tests/test_propagation_standalone.py --sfi 70

# Solar maximum  
python3 tests/test_propagation_standalone.py --sfi 220

# Geomagnetic storm
python3 tests/test_propagation_standalone.py --sfi 150 --k 7 --r R3

# All edge cases (7 scenarios)
python3 tests/test_propagation_standalone.py --edge-cases
```

**Parameters:**
- `--sfi N` - Solar Flux Index (70-250, default: 145)
- `--k N` - K-index (0-9, default: 2.0)
- `--r RN` - R-scale (R0-R5, default: R0)
- `--hour N` - UTC hour (0-23, default: current)
- `--edge-cases` - Run predefined scenarios

**Tests:**
- foF2 (critical frequency) calculation
- MUF (maximum usable frequency) for various distances
- D-layer absorption modeling
- Gray line detection
- K-index frequency-dependent impact
- Seasonal propagation factors
- Band-by-band quality predictions (160m-6m)

**Output:** Step-by-step calculations, band predictions table, operating recommendations

## Running All Tests

```bash
# From project root
for test in tests/test_*.py; do
    echo "Running $test..."
    python "$test"
    echo "---"
done
```

## Adding New Tests

1. Create `test_<feature>.py` in this directory
2. Follow the naming convention: `test_<component>.py`
3. Add documentation to this README
4. Use descriptive assertions and error messages
