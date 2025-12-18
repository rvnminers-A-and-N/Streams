# Satori Streams

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Data stream sources for the Satori Network. This repository contains oracle scripts that fetch external data and publish observations to the network.

## Overview

**Oracles** are nodes that bring external data into the Satori Network. They fetch real-world data (economic indicators, prices, sensor readings, etc.) and publish it as **observations** that other nodes can make predictions on.

```
External Data Source → Oracle Script → Observation → Satori Network → Predictions
```

## Structure

```
Streams/
├── historic/           # 2,400+ FRED economic data stream scripts
│   ├── 10_Year_Treasury_Constant_Maturity_Rate.py
│   ├── Federal_Funds_Rate.py
│   └── ...
└── scripts/            # Utilities and P2P publishing tools
    ├── p2p_publisher.py        # P2P/HTTP observation publisher
    ├── example_p2p_stream.py   # Example oracle implementation
    └── P2P_PUBLISHING.md       # P2P publishing documentation
```

## Historic Streams

The `historic/` folder contains **2,400+ pre-built oracle scripts** for FRED (Federal Reserve Economic Data) series. Each script:

1. Fetches historical data from the FRED API
2. Exports to CSV format
3. Provides a `postRequestHook()` function for real-time value extraction

### Example: 10-Year Treasury Rate

```python
# Fetch latest value
import requests

url = "https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key=YOUR_KEY&file_type=json"
response = requests.get(url)
data = response.json()

# Get latest observation
latest = data['observations'][-1]
print(f"10-Year Treasury: {latest['value']}%")
```

### Available Data Categories

| Category | Examples |
|----------|----------|
| **Interest Rates** | Treasury rates (1mo-30yr), SOFR, Fed Funds, AMERIBOR |
| **Inflation** | CPI, Breakeven rates, TIPS |
| **Mortgages** | 15yr/30yr fixed, FHA, VA, Jumbo |
| **Commercial Paper** | AA/A2 Financial/Nonfinancial rates |
| **Swaps** | Interest rate swaps (1yr-30yr) |
| **Economic Indicators** | GDP, Employment, Retail sales |

## P2P Publishing

The `scripts/` folder provides tools for publishing observations via P2P networking.

### Networking Modes

| Mode | Description |
|------|-------------|
| `central` | HTTP only - sends to central server (default) |
| `hybrid` | P2P first with HTTP fallback (recommended) |
| `p2p` | Pure P2P - fully decentralized |

Set the mode via environment variable:
```bash
export SATORI_NETWORKING_MODE=hybrid
```

### Quick Start

```python
from scripts.p2p_publisher import publish

# Publish an observation
result = publish(
    stream_id="fred|myname|DGS10|rate",
    value=4.25
)

if result.success:
    print(f"Published via {result.method}")
```

### Stream ID Format

Stream IDs follow the format: `source|author|stream|target`

| Component | Description | Example |
|-----------|-------------|---------|
| `source` | Data origin | `fred`, `crypto`, `sensors` |
| `author` | Publisher identifier | `satori`, `myname` |
| `stream` | What's being measured | `DGS10`, `BTC`, `temperature` |
| `target` | Specific target | `rate`, `USD`, `outdoor` |

**Examples:**
- `fred|satori|DGS10|rate` - 10-Year Treasury Rate
- `crypto|satori|BTC|USD` - Bitcoin price in USD
- `sensors|home|temperature|outdoor` - Outdoor temperature sensor

## Creating Your Own Oracle

### Step 1: Create the Data Fetcher

```python
import requests
from scripts.p2p_publisher import P2PPublisher

async def fetch_my_data():
    """Fetch data from your source."""
    response = requests.get("https://api.example.com/data")
    return float(response.json()['value'])

async def run_oracle():
    publisher = P2PPublisher()
    await publisher.start()

    while True:
        value = await fetch_my_data()

        result = await publisher.publish_observation(
            stream_id="myapi|myname|metric|target",
            value=value
        )

        print(f"Published: {value} via {result.method}")
        await asyncio.sleep(300)  # Poll every 5 minutes
```

### Step 2: Register Your Stream

To have your stream officially recognized:

1. Create a script in `historic/` following the naming convention
2. Include both historical CSV export and real-time `postRequestHook()`
3. Submit a pull request

## Using with satori-lite

The `streams-lite` module in [satori-lite](https://github.com/SatoriNetwork/satori-lite) provides a complete oracle framework that integrates with this repository's data sources:

```yaml
# streams.yaml configuration
enabled: true
oracles:
  - type: fred
    name: 10-Year Treasury Rate
    stream_id: fred|satori|DGS10|rate
    poll_interval: 3600
    extra:
      series_id: DGS10
```

See the [satori-lite documentation](https://github.com/SatoriNetwork/satori-lite#streams-lite-oracle-framework) for more details.

## FRED API

Most historic streams use the [FRED API](https://fred.stlouisfed.org/docs/api/fred/).

### Getting an API Key

1. Visit https://fred.stlouisfed.org/docs/api/api_key.html
2. Create a free account
3. Request an API key
4. Set it in your environment: `export FRED_API_KEY=your_key_here`

### Rate Limits

- Free tier: 120 requests per minute
- Be respectful of rate limits when running multiple oracles

## Requirements

```bash
pip install requests
pip install satorip2p  # For P2P publishing (optional)
```

## Contributing

We welcome new stream sources! To contribute:

1. Fork this repository
2. Create your stream script in `historic/` or `scripts/`
3. Follow the existing naming conventions
4. Include both historical data export and real-time fetching
5. Submit a pull request

### Naming Convention

- Use descriptive names with underscores: `10_Year_Treasury_Constant_Maturity_Rate.py`
- Match the official FRED series name when applicable

## Related Repositories

- [satori-lite](https://github.com/SatoriNetwork/satori-lite) - Lightweight neuron with oracle framework
- [satorip2p](https://github.com/SatoriNetwork/satorip2p) - P2P networking library
- [Neuron](https://github.com/SatoriNetwork/Neuron) - Full neuron implementation

## License

MIT License - see LICENSE file for details.

## Support

- GitHub Issues: https://github.com/SatoriNetwork/Streams/issues
- Documentation: https://satorinet.io/docs
