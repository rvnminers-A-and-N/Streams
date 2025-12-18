"""
P2P Publisher Utility for Satori Streams

Enables direct P2P publishing of observations without going through HTTP.
Supports hybrid mode (P2P + HTTP fallback) and pure P2P mode.

Usage:
    from p2p_publisher import P2PPublisher

    publisher = P2PPublisher()
    await publisher.start()

    # Publish an observation
    await publisher.publish_observation(
        stream_id="source|author|stream|target",
        value=42.5,
        timestamp=1234567890
    )

    # Or use the sync wrapper
    publisher.publish_sync(stream_id, value)
"""

import os
import time
import json
import asyncio
import logging
import requests
from typing import Optional, Dict, Any, Union
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PublishResult:
    """Result of a publish operation."""
    success: bool
    method: str  # 'p2p', 'http', 'both'
    message: str
    p2p_success: bool = False
    http_success: bool = False


def get_networking_mode() -> str:
    """Get the current networking mode from environment or default to central."""
    return os.environ.get('SATORI_NETWORKING_MODE', 'central').lower().strip()


class P2PPublisher:
    """
    Publisher that can send observations via P2P network and/or HTTP.

    Modes:
    - central: HTTP only (default)
    - hybrid: P2P first, HTTP fallback
    - p2p: P2P only
    """

    def __init__(
        self,
        wallet_path: str = None,
        neuron_url: str = 'http://localhost:24601',
        p2p_port: int = 24600,
    ):
        """
        Initialize the P2P publisher.

        Args:
            wallet_path: Path to wallet.yaml for P2P identity
            neuron_url: URL of local Neuron for HTTP fallback
            p2p_port: Port for P2P networking
        """
        self.wallet_path = wallet_path or os.path.expanduser('~/.satori/wallet/wallet.yaml')
        self.neuron_url = neuron_url
        self.p2p_port = p2p_port
        self.mode = get_networking_mode()

        # P2P components (lazy initialized)
        self._peers = None
        self._oracle_network = None
        self._identity = None
        self._started = False

    async def start(self):
        """Initialize P2P components if in hybrid/p2p mode."""
        if self._started:
            return

        if self.mode in ('hybrid', 'p2p', 'p2p_only'):
            try:
                await self._init_p2p()
                logger.info(f"P2P publisher started in {self.mode} mode")
            except ImportError:
                logger.warning("satorip2p not installed, falling back to HTTP only")
                self.mode = 'central'
            except Exception as e:
                logger.warning(f"Failed to initialize P2P: {e}, falling back to HTTP")
                self.mode = 'central'

        self._started = True

    async def _init_p2p(self):
        """Initialize P2P networking components."""
        from satorip2p import Peers
        from satorip2p.protocol.oracle_network import OracleNetwork
        from satorilib.wallet.evrmore.identity import EvrmoreIdentity

        # Load identity from wallet
        if os.path.exists(self.wallet_path):
            self._identity = EvrmoreIdentity(self.wallet_path)
        else:
            logger.warning(f"Wallet not found at {self.wallet_path}")
            raise FileNotFoundError(f"Wallet not found: {self.wallet_path}")

        # Initialize P2P peers
        self._peers = Peers(
            identity=self._identity,
            listen_port=self.p2p_port,
        )
        await self._peers.start()

        # Initialize oracle network for publishing observations
        self._oracle_network = OracleNetwork(self._peers)
        await self._oracle_network.start()

        logger.info("P2P components initialized")

    async def stop(self):
        """Stop P2P components."""
        if self._oracle_network:
            try:
                await self._oracle_network.stop()
            except Exception:
                pass
        if self._peers:
            try:
                await self._peers.stop()
            except Exception:
                pass
        self._started = False

    async def publish_observation(
        self,
        stream_id: str,
        value: float,
        timestamp: int = None,
        metadata: Dict[str, Any] = None,
    ) -> PublishResult:
        """
        Publish an observation to the network.

        Args:
            stream_id: Stream identifier (format: "source|author|stream|target")
            value: Observed value
            timestamp: Unix timestamp (default: now)
            metadata: Optional metadata dict

        Returns:
            PublishResult with success status and method used
        """
        if not self._started:
            await self.start()

        timestamp = timestamp or int(time.time())
        p2p_success = False
        http_success = False
        messages = []

        # Try P2P first if in hybrid/p2p mode
        if self.mode in ('hybrid', 'p2p', 'p2p_only') and self._oracle_network:
            try:
                observation = await self._oracle_network.publish_observation(
                    stream_id=stream_id,
                    value=value,
                    timestamp=timestamp,
                )
                if observation:
                    p2p_success = True
                    messages.append("P2P publish successful")
                    logger.debug(f"Published via P2P: {stream_id} = {value}")
            except Exception as e:
                messages.append(f"P2P publish failed: {e}")
                logger.warning(f"P2P publish failed: {e}")

        # Try HTTP if in central/hybrid mode or P2P failed
        if self.mode == 'central' or (self.mode == 'hybrid' and not p2p_success):
            try:
                http_success = self._publish_http(stream_id, value, timestamp, metadata)
                if http_success:
                    messages.append("HTTP publish successful")
            except Exception as e:
                messages.append(f"HTTP publish failed: {e}")
                logger.warning(f"HTTP publish failed: {e}")

        # Determine result
        success = p2p_success or http_success
        if p2p_success and http_success:
            method = 'both'
        elif p2p_success:
            method = 'p2p'
        elif http_success:
            method = 'http'
        else:
            method = 'none'

        return PublishResult(
            success=success,
            method=method,
            message='; '.join(messages),
            p2p_success=p2p_success,
            http_success=http_success,
        )

    def _publish_http(
        self,
        stream_id: str,
        value: float,
        timestamp: int,
        metadata: Dict[str, Any] = None,
    ) -> bool:
        """Publish observation via HTTP to local Neuron."""
        try:
            # Parse stream_id
            parts = stream_id.split('|')
            if len(parts) >= 4:
                source, author, stream, target = parts[0], parts[1], parts[2], parts[3]
            else:
                source, author, stream, target = 'satori', '', stream_id, ''

            # Prepare payload
            payload = {
                'source': source,
                'author': author,
                'stream': stream,
                'target': target,
                'value': str(value),
                'timestamp': str(timestamp),
            }
            if metadata:
                payload['metadata'] = json.dumps(metadata)

            # Post to Neuron
            url = f"{self.neuron_url}/relay/submit"
            response = requests.post(url, data=payload, timeout=10)

            if response.ok:
                logger.debug(f"Published via HTTP: {stream_id} = {value}")
                return True
            else:
                logger.warning(f"HTTP publish returned {response.status_code}")
                return False

        except requests.RequestException as e:
            logger.warning(f"HTTP request failed: {e}")
            return False

    def publish_sync(
        self,
        stream_id: str,
        value: float,
        timestamp: int = None,
        metadata: Dict[str, Any] = None,
    ) -> PublishResult:
        """
        Synchronous wrapper for publish_observation.

        Use this when you don't have an async context.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Already in async context, create task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.publish_observation(stream_id, value, timestamp, metadata)
                    )
                    return future.result(timeout=30)
            else:
                return loop.run_until_complete(
                    self.publish_observation(stream_id, value, timestamp, metadata)
                )
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(
                self.publish_observation(stream_id, value, timestamp, metadata)
            )


# Convenience functions for simple usage
_default_publisher = None


def get_publisher() -> P2PPublisher:
    """Get or create the default publisher instance."""
    global _default_publisher
    if _default_publisher is None:
        _default_publisher = P2PPublisher()
    return _default_publisher


def publish(
    stream_id: str,
    value: float,
    timestamp: int = None,
) -> PublishResult:
    """
    Publish an observation using the default publisher.

    Simple convenience function for quick publishing.

    Args:
        stream_id: Stream identifier
        value: Observed value
        timestamp: Unix timestamp (default: now)

    Returns:
        PublishResult
    """
    publisher = get_publisher()
    return publisher.publish_sync(stream_id, value, timestamp)


# Example usage and CLI
if __name__ == '__main__':
    import sys

    if len(sys.argv) < 3:
        print("Usage: python p2p_publisher.py <stream_id> <value> [timestamp]")
        print("Example: python p2p_publisher.py 'fred|satori|DGS10|rate' 4.25")
        print("")
        print("Environment variables:")
        print("  SATORI_NETWORKING_MODE: central, hybrid, or p2p (default: central)")
        sys.exit(1)

    stream_id = sys.argv[1]
    value = float(sys.argv[2])
    timestamp = int(sys.argv[3]) if len(sys.argv) > 3 else None

    # Configure logging
    logging.basicConfig(level=logging.INFO)

    # Publish
    result = publish(stream_id, value, timestamp)

    if result.success:
        print(f"✓ Published successfully via {result.method}")
    else:
        print(f"✗ Publish failed: {result.message}")
        sys.exit(1)
