# P2P Publishing for Satori Streams

This directory contains utilities for publishing data stream observations directly to the Satori P2P network.

## Overview

Traditional Satori oracles publish observations via HTTP to the local Neuron at `http://localhost:24601`. With P2P publishing, observations can be broadcast directly to the decentralized network, enabling:

- **True decentralization**: No single point of failure
- **Lower latency**: Direct peer-to-peer transmission
- **Redundancy**: Multiple network paths for delivery
- **Hybrid mode**: P2P with HTTP fallback for reliability

## Files

- `p2p_publisher.py` - Core P2P publishing utility
- `example_p2p_stream.py` - Example oracle implementations (FRED, generic HTTP)

## Quick Start

### 1. Simple Publishing

```python
from p2p_publisher import publish

# Publish a single observation
result = publish(
    stream_id="source|author|stream|target",
    value=42.5,
)

if result.success:
    print(f"Published via {result.method}")
```

### 2. Using the Publisher Class

```python
from p2p_publisher import P2PPublisher
import asyncio

async def main():
    publisher = P2PPublisher()
    await publisher.start()

    result = await publisher.publish_observation(
        stream_id="fred|satori|DGS10|rate",
        value=4.25,
    )

    await publisher.stop()

asyncio.run(main())
```

### 3. Command Line

```bash
# Central mode (HTTP only)
python p2p_publisher.py "fred|satori|DGS10|rate" 4.25

# Hybrid mode (P2P with HTTP fallback)
SATORI_NETWORKING_MODE=hybrid python p2p_publisher.py "fred|satori|DGS10|rate" 4.25

# Pure P2P mode
SATORI_NETWORKING_MODE=p2p python p2p_publisher.py "fred|satori|DGS10|rate" 4.25
```

## Networking Modes

Set via environment variable `SATORI_NETWORKING_MODE`:

| Mode | Description |
|------|-------------|
| `central` | HTTP only (default, legacy) |
| `hybrid` | P2P first, HTTP fallback (recommended) |
| `p2p` | P2P only, no HTTP |

## Creating a Custom Oracle

```python
from p2p_publisher import P2PPublisher
import asyncio

class MyOracle:
    def __init__(self):
        self.publisher = P2PPublisher()
        self.stream_id = "mydata|satori|temperature|sensor1"

    async def start(self):
        await self.publisher.start()

    async def publish_reading(self, value: float):
        result = await self.publisher.publish_observation(
            stream_id=self.stream_id,
            value=value,
        )
        return result.success

    async def stop(self):
        await self.publisher.stop()
```

## Requirements

For P2P mode, you need:

1. `satorip2p` package installed
2. A wallet at `~/.satori/wallet/wallet.yaml` (or specify path)
3. Network connectivity for P2P peers

For central/hybrid mode HTTP fallback:
1. Local Neuron running at `http://localhost:24601`

## Integration with Existing Scripts

To add P2P support to an existing stream script:

1. Import the publisher:
   ```python
   from p2p_publisher import publish
   ```

2. Replace HTTP uploads with:
   ```python
   result = publish(stream_id, value)
   ```

3. Set networking mode via environment:
   ```bash
   SATORI_NETWORKING_MODE=hybrid python your_script.py
   ```

## Architecture

```
┌─────────────────┐
│   Data Source   │  (FRED, exchange API, sensor, etc.)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│     Oracle      │  (Your script)
│   fetch data    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  P2PPublisher   │
│   ┌─────────┐   │
│   │  mode?  │   │
│   └────┬────┘   │
│   ┌────┴────┐   │
│   ▼         ▼   │
│ P2P       HTTP  │
│ Network   POST  │
└────┬────────┬───┘
     │        │
     ▼        ▼
┌─────────┐ ┌─────────┐
│  Peers  │ │ Neuron  │
│ (DHT/   │ │ (local) │
│ GossipSub)│         │
└─────────┘ └─────────┘
```

## See Also

- [satorip2p documentation](https://github.com/SatoriNetwork/satorip2p)
- [Satori Network](https://satorinet.io)
