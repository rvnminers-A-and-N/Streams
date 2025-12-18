"""
Example P2P-enabled Data Stream

This example shows how to modify an existing data stream script to publish
observations via P2P network instead of (or in addition to) HTTP.

Based on the 10-Year Treasury Rate stream, but generalized for any data source.

Usage:
    # Central mode (HTTP only) - default
    python example_p2p_stream.py

    # Hybrid mode (P2P with HTTP fallback)
    SATORI_NETWORKING_MODE=hybrid python example_p2p_stream.py

    # Pure P2P mode
    SATORI_NETWORKING_MODE=p2p python example_p2p_stream.py
"""

import os
import sys
import json
import time
import logging
import requests
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from p2p_publisher import P2PPublisher, get_networking_mode

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DataStreamOracle:
    """
    Base class for data stream oracles.

    Oracles fetch data from external sources and publish observations
    to the Satori network via P2P and/or HTTP.
    """

    def __init__(
        self,
        stream_id: str,
        source_url: str,
        poll_interval: int = 3600,  # 1 hour default
    ):
        """
        Initialize the oracle.

        Args:
            stream_id: Unique stream identifier (source|author|stream|target)
            source_url: URL to fetch data from
            poll_interval: Seconds between polls
        """
        self.stream_id = stream_id
        self.source_url = source_url
        self.poll_interval = poll_interval
        self.publisher = P2PPublisher()
        self.last_value = None
        self.last_publish_time = 0

    async def start(self):
        """Start the oracle (initializes P2P if needed)."""
        await self.publisher.start()
        logger.info(f"Oracle started for {self.stream_id}")
        logger.info(f"Networking mode: {get_networking_mode()}")

    async def stop(self):
        """Stop the oracle."""
        await self.publisher.stop()
        logger.info(f"Oracle stopped for {self.stream_id}")

    def fetch_latest_value(self) -> float:
        """
        Fetch the latest value from the data source.

        Override this method for custom data sources.

        Returns:
            The latest observation value
        """
        raise NotImplementedError("Subclasses must implement fetch_latest_value()")

    async def poll_and_publish(self):
        """Fetch latest value and publish if changed."""
        try:
            value = self.fetch_latest_value()

            if value is None:
                logger.warning("No value fetched")
                return

            # Only publish if value changed or enough time passed
            now = time.time()
            if (
                value != self.last_value or
                now - self.last_publish_time > self.poll_interval
            ):
                result = await self.publisher.publish_observation(
                    stream_id=self.stream_id,
                    value=value,
                    timestamp=int(now),
                )

                if result.success:
                    logger.info(f"Published: {self.stream_id} = {value} via {result.method}")
                    self.last_value = value
                    self.last_publish_time = now
                else:
                    logger.error(f"Failed to publish: {result.message}")

        except Exception as e:
            logger.error(f"Poll and publish error: {e}")

    async def run_forever(self):
        """Run the oracle continuously."""
        await self.start()

        try:
            while True:
                await self.poll_and_publish()
                await asyncio.sleep(self.poll_interval)
        except KeyboardInterrupt:
            logger.info("Interrupted, stopping...")
        finally:
            await self.stop()


class FREDOracle(DataStreamOracle):
    """
    Oracle for FRED (Federal Reserve Economic Data) series.

    Example data sources:
    - DGS10: 10-Year Treasury Constant Maturity Rate
    - DGS2: 2-Year Treasury Constant Maturity Rate
    - FEDFUNDS: Federal Funds Rate
    - CPIAUCSL: Consumer Price Index
    """

    def __init__(
        self,
        series_id: str,
        api_key: str,
        stream_name: str = None,
        poll_interval: int = 3600,
    ):
        """
        Initialize FRED oracle.

        Args:
            series_id: FRED series ID (e.g., "DGS10")
            api_key: FRED API key
            stream_name: Optional custom stream name (default: series_id)
            poll_interval: Seconds between polls
        """
        self.series_id = series_id
        self.api_key = api_key

        stream_id = f"fred|satori|{stream_name or series_id}|rate"
        source_url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series_id}&api_key={api_key}&file_type=json"
        )

        super().__init__(stream_id, source_url, poll_interval)

    def fetch_latest_value(self) -> float:
        """Fetch latest value from FRED API."""
        try:
            response = requests.get(self.source_url, timeout=30)
            response.raise_for_status()

            data = response.json()
            observations = data.get('observations', [])

            # Find latest non-empty value
            for obs in reversed(observations):
                try:
                    value = float(obs['value'])
                    return value
                except (ValueError, KeyError):
                    continue

            return None

        except requests.RequestException as e:
            logger.error(f"FRED API error: {e}")
            return None


class GenericHTTPOracle(DataStreamOracle):
    """
    Generic oracle for any HTTP JSON endpoint.

    Configure the JSON path to extract the value.
    """

    def __init__(
        self,
        stream_id: str,
        source_url: str,
        json_path: str = 'value',
        poll_interval: int = 3600,
        headers: dict = None,
    ):
        """
        Initialize generic HTTP oracle.

        Args:
            stream_id: Stream identifier
            source_url: URL to fetch JSON from
            json_path: Dot-separated path to value in JSON (e.g., "data.price")
            poll_interval: Seconds between polls
            headers: Optional HTTP headers
        """
        super().__init__(stream_id, source_url, poll_interval)
        self.json_path = json_path
        self.headers = headers or {}

    def _extract_value(self, data: dict, path: str):
        """Extract value from nested dict using dot notation."""
        keys = path.split('.')
        result = data
        for key in keys:
            if isinstance(result, dict):
                result = result.get(key)
            elif isinstance(result, list) and key.isdigit():
                result = result[int(key)]
            else:
                return None
        return result

    def fetch_latest_value(self) -> float:
        """Fetch latest value from HTTP endpoint."""
        try:
            response = requests.get(
                self.source_url,
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()

            data = response.json()
            value = self._extract_value(data, self.json_path)

            if value is not None:
                return float(value)
            return None

        except (requests.RequestException, ValueError) as e:
            logger.error(f"HTTP fetch error: {e}")
            return None


# Import asyncio for async operations
import asyncio


async def main():
    """Example: Run a FRED oracle for the 10-Year Treasury Rate."""

    # Your FRED API key (get one at https://fred.stlouisfed.org/docs/api/api_key.html)
    # For demo, using the key from the original script
    api_key = os.environ.get('FRED_API_KEY', '7ef44306675240d156b2b8786339b867')

    # Create oracle
    oracle = FREDOracle(
        series_id='DGS10',
        api_key=api_key,
        stream_name='10_Year_Treasury_Rate',
        poll_interval=3600,  # 1 hour
    )

    print(f"Starting FRED oracle for DGS10 (10-Year Treasury Rate)")
    print(f"Networking mode: {get_networking_mode()}")
    print("Press Ctrl+C to stop\n")

    # Run once for demo, or run_forever for production
    await oracle.start()
    await oracle.poll_and_publish()
    await oracle.stop()

    print("\nDone. To run continuously, call oracle.run_forever()")


if __name__ == '__main__':
    asyncio.run(main())
