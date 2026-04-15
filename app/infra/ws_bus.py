"""
WebSocket Communication Layer for TudouClaw Distributed Architecture.

This module provides the communication backbone for TudouClaw's Master-Node
distributed system. It handles:
- Master-side WebSocket server (WSBusServer) for accepting Node connections
- Node-side WebSocket client (WSBusClient) for connecting to Master
- Unified JSON message protocol with ACK tracking and heartbeat
- Thread-safe interfaces for sync code via asyncio thread
- Graceful degradation when websockets library is not available

The module requires Python 3.7+ and asyncio. The 'websockets' library is
optional but required for distributed mode.
"""

import asyncio
import json
import logging
import os
import threading
import uuid
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Callable, Dict, Optional, Any, List
from queue import Queue, Empty
from collections import defaultdict

from ..defaults import (
    WS_BUS_PORT, WS_ACK_TIMEOUT, WS_PING_TIMEOUT,
    WS_MASTER_URL, BIND_ADDRESS,
)

# Try to import websockets, but allow graceful degradation
try:
    import websockets
    from websockets.server import WebSocketServerProtocol
    from websockets.client import WebSocketClientProtocol
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    WebSocketServerProtocol = None
    WebSocketClientProtocol = None

logger = logging.getLogger("tudou.ws_bus")


# ============================================================================
# Message Type Constants
# ============================================================================

class MessageType(str, Enum):
    """Enumeration of all message types in the protocol."""
    # Node lifecycle
    NODE_REGISTER = "node.register"
    NODE_HEARTBEAT = "node.heartbeat"

    # Configuration sync
    CONFIG_SYNC = "config.sync"
    CONFIG_FULL_SYNC = "config.full_sync"

    # Agent management
    AGENT_DISPATCH = "agent.dispatch"
    AGENT_RECALL = "agent.recall"
    AGENT_MESSAGE = "agent.message"
    AGENT_STATUS = "agent.status"

    # Event broadcast
    EVENT_BROADCAST = "event.broadcast"

    # File operations
    FILE_UPLOAD = "file.upload"
    FILE_UPLOAD_ACK = "file.upload_ack"

    # Task management
    TASK_ASSIGN = "task.assign"
    TASK_RESULT = "task.result"

    # LLM proxy
    LLM_PROXY_REQUEST = "llm.proxy_request"
    LLM_PROXY_CHUNK = "llm.proxy_chunk"

    # Protocol
    ACK = "ack"


# ============================================================================
# Message Envelope
# ============================================================================

@dataclass
class Message:
    """Unified message envelope for all WebSocket communication."""
    type: str
    id: str
    sender: str
    recipient: str
    timestamp: float
    payload: Dict[str, Any]
    require_ack: bool = False

    def to_json(self) -> str:
        """Serialize message to JSON string."""
        data = asdict(self)
        return json.dumps(data)

    @classmethod
    def from_json(cls, json_str: str) -> 'Message':
        """Deserialize message from JSON string."""
        data = json.loads(json_str)
        return cls(**data)

    @classmethod
    def create(
        cls,
        msg_type: str,
        sender: str,
        recipient: str,
        payload: Dict[str, Any],
        require_ack: bool = False,
        msg_id: Optional[str] = None
    ) -> 'Message':
        """Create a new message with automatic ID and timestamp."""
        return cls(
            type=msg_type,
            id=msg_id or f"msg-{uuid.uuid4().hex[:12]}",
            sender=sender,
            recipient=recipient,
            timestamp=time.time(),
            payload=payload,
            require_ack=require_ack
        )


# ============================================================================
# Base Connection Class
# ============================================================================

class WSConnection(ABC):
    """Abstract base for WebSocket connections."""

    def __init__(self, node_id: str):
        self.node_id = node_id
        self.connected = False
        self._handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._pending_acks: Dict[str, asyncio.Future] = {}
        self._ack_timeout = WS_ACK_TIMEOUT

    def on(self, msg_type: str, callback: Callable) -> None:
        """Register a handler for a specific message type."""
        self._handlers[msg_type].append(callback)

    def off(self, msg_type: str, callback: Callable) -> None:
        """Unregister a handler."""
        if msg_type in self._handlers:
            try:
                self._handlers[msg_type].remove(callback)
            except ValueError:
                pass

    async def _dispatch_message(self, message: Message) -> None:
        """Dispatch received message to registered handlers."""
        handlers = self._handlers.get(message.type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(message)
                else:
                    handler(message)
            except Exception as e:
                logger.error(
                    f"Error in message handler for {message.type}: {e}",
                    exc_info=True
                )

    @abstractmethod
    async def send(self, message: Message) -> None:
        """Send a message. To be implemented by subclasses."""
        pass


# ============================================================================
# WebSocket Server (Master Side)
# ============================================================================

class WSBusServer(WSConnection):
    """
    WebSocket server for Master node.

    Accepts connections from Node instances, authenticates them, and routes
    messages between nodes or broadcasts to all connected nodes.
    """

    def __init__(
        self,
        node_id: str = "master",
        host: str = BIND_ADDRESS,
        port: int = WS_BUS_PORT,
        secret: Optional[str] = None
    ):
        super().__init__(node_id)

        if not WEBSOCKETS_AVAILABLE:
            raise RuntimeError(
                "websockets library is required for distributed mode. "
                "Install it with: pip install websockets"
            )

        self.host = host
        self.port = port
        self.secret = secret or os.environ.get("TUDOU_WS_SECRET", "default-secret")

        # Connected nodes: {node_id: websocket}
        self._connected_nodes: Dict[str, WebSocketServerProtocol] = {}
        self._node_lock = threading.Lock()

        self._server = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

    async def start(self) -> None:
        """Start the WebSocket server."""
        async def handler(ws: WebSocketServerProtocol, path: str):
            await self._handle_connection(ws)

        self._server = await websockets.serve(
            handler,
            self.host,
            self.port,
            ping_interval=10,
            ping_timeout=5
        )
        logger.info(f"WSBusServer started on {self.host}:{self.port}")

    async def stop(self) -> None:
        """Stop the WebSocket server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("WSBusServer stopped")

    async def _handle_connection(self, ws: WebSocketServerProtocol) -> None:
        """Handle a new node connection."""
        node_id = None

        try:
            # Authenticate via header or first message
            auth_header = ws.request_headers.get("X-Claw-Secret")
            if auth_header and auth_header != self.secret:
                logger.warning(f"Authentication failed for {ws.remote_address}")
                await ws.close(code=4001, reason="Unauthorized")
                return

            # Receive first message (node registration)
            first_msg_str = await ws.recv()
            first_msg = Message.from_json(first_msg_str)

            if first_msg.type != MessageType.NODE_REGISTER:
                logger.error("First message must be NODE_REGISTER")
                await ws.close(code=4002, reason="Invalid first message")
                return

            node_id = first_msg.sender

            with self._node_lock:
                self._connected_nodes[node_id] = ws

            logger.info(f"Node {node_id} connected")
            self.connected = True

            # Message loop
            async for msg_str in ws:
                try:
                    message = Message.from_json(msg_str)
                    await self._handle_message(message)
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON from {node_id}: {e}")
                except Exception as e:
                    logger.error(f"Error handling message from {node_id}: {e}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Connection error for {node_id}: {e}")
        finally:
            if node_id:
                with self._node_lock:
                    self._connected_nodes.pop(node_id, None)
                logger.info(f"Node {node_id} disconnected")

    async def _handle_message(self, message: Message) -> None:
        """Handle an incoming message from a node."""
        # Dispatch to handlers
        await self._dispatch_message(message)

        # Route message if needed
        if message.recipient == "master":
            # Message for master, handlers will deal with it
            pass
        elif message.recipient == "broadcast":
            # Broadcast to all nodes
            await self.broadcast(message)
        else:
            # Send to specific node
            await self.send_to_node(message.recipient, message)

        # Send ACK if required
        if message.require_ack:
            ack = Message.create(
                msg_type=MessageType.ACK,
                sender="master",
                recipient=message.sender,
                payload={"ack_id": message.id}
            )
            await self.send_to_node(message.sender, ack)

    async def send_to_node(self, node_id: str, message: Message) -> None:
        """Send a message to a specific node."""
        with self._node_lock:
            ws = self._connected_nodes.get(node_id)

        if not ws:
            logger.warning(f"Node {node_id} not connected")
            return

        try:
            await ws.send(message.to_json())
            logger.debug(f"Sent {message.type} to {node_id}")
        except Exception as e:
            logger.error(f"Failed to send message to {node_id}: {e}")

    async def broadcast(self, message: Message) -> None:
        """Broadcast a message to all connected nodes."""
        with self._node_lock:
            nodes = list(self._connected_nodes.items())

        for node_id, ws in nodes:
            try:
                await ws.send(message.to_json())
            except Exception as e:
                logger.error(f"Failed to broadcast to {node_id}: {e}")

    async def send(self, message: Message) -> None:
        """Send a message (routes to recipient)."""
        if message.recipient == "broadcast":
            await self.broadcast(message)
        else:
            await self.send_to_node(message.recipient, message)

    def start_async(self) -> None:
        """Start the server in a background thread."""
        def run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            try:
                self._loop.run_until_complete(self.start())
                self._loop.run_forever()
            except Exception as e:
                logger.error(f"Server loop error: {e}")
            finally:
                self._loop.close()

        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()
        time.sleep(0.5)  # Give server time to start

    def stop_async(self) -> None:
        """Stop the server and wait for thread to finish."""
        if self._loop:
            asyncio.run_coroutine_threadsafe(self.stop(), self._loop)
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread:
            self._thread.join(timeout=5)


# ============================================================================
# WebSocket Client (Node Side)
# ============================================================================

class WSBusClient(WSConnection):
    """
    WebSocket client for Node instances.

    Connects to Master, maintains connection with auto-reconnect and
    exponential backoff, sends/receives messages with handlers.
    """

    def __init__(
        self,
        node_id: str,
        master_url: str = WS_MASTER_URL,
        secret: Optional[str] = None,
        max_retries: int = -1,  # -1 = infinite
        initial_backoff: float = 1.0,
        max_backoff: float = 30.0
    ):
        super().__init__(node_id)

        if not WEBSOCKETS_AVAILABLE:
            raise RuntimeError(
                "websockets library is required for distributed mode. "
                "Install it with: pip install websockets"
            )

        self.master_url = master_url
        self.secret = secret or os.environ.get("TUDOU_WS_SECRET", "default-secret")
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff

        self._ws: Optional[WebSocketClientProtocol] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._tx_queue: Queue = Queue()
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._connect_task: Optional[asyncio.Task] = None

    async def _connect(self) -> None:
        """Attempt to connect to the master with exponential backoff."""
        retries = 0
        backoff = self.initial_backoff

        while True:
            try:
                headers = {"X-Claw-Secret": self.secret}
                self._ws = await websockets.connect(
                    self.master_url,
                    extra_headers=headers,
                    ping_interval=10,
                    ping_timeout=5
                )

                logger.info(f"Connected to master at {self.master_url}")
                self.connected = True

                # Send registration message
                reg_msg = Message.create(
                    msg_type=MessageType.NODE_REGISTER,
                    sender=self.node_id,
                    recipient="master",
                    payload={"node_id": self.node_id}
                )
                await self._ws.send(reg_msg.to_json())

                # Start message handlers
                await self._message_loop()

            except Exception as e:
                self.connected = False
                logger.warning(f"Connection failed: {e}")

                if self.max_retries >= 0 and retries >= self.max_retries:
                    logger.error(f"Max retries ({self.max_retries}) reached")
                    break

                retries += 1
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self.max_backoff)

    async def _message_loop(self) -> None:
        """Main message receive loop."""
        assert self._ws is not None

        try:
            async for msg_str in self._ws:
                try:
                    message = Message.from_json(msg_str)
                    await self._dispatch_message(message)
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON received: {e}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Message loop error: {e}")

    async def _send_loop(self) -> None:
        """Background loop to send queued messages."""
        while True:
            try:
                # Non-blocking check with timeout
                message = self._tx_queue.get(timeout=0.1)

                if self._ws and self.connected:
                    await self._ws.send(message.to_json())
                    logger.debug(f"Sent {message.type} to master")
                else:
                    # Requeue if not connected
                    self._tx_queue.put(message)
                    await asyncio.sleep(0.5)

            except Empty:
                await asyncio.sleep(0.01)
            except Exception as e:
                logger.error(f"Send loop error: {e}")

    async def _heartbeat_loop(self) -> None:
        """Send heartbeat messages periodically."""
        while True:
            try:
                await asyncio.sleep(10)

                if self.connected:
                    hb = Message.create(
                        msg_type=MessageType.NODE_HEARTBEAT,
                        sender=self.node_id,
                        recipient="master",
                        payload={"timestamp": time.time()}
                    )
                    await self.send(hb)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")

    async def send(self, message: Message) -> None:
        """Queue a message to be sent."""
        self._tx_queue.put(message)

    def send_sync(self, message: Message) -> None:
        """Thread-safe send from synchronous code."""
        self._tx_queue.put(message)

    def start_async(self) -> None:
        """Start the client in a background thread."""
        def run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            try:
                self._loop.run_until_complete(self._run())
            except Exception as e:
                logger.error(f"Client loop error: {e}")
            finally:
                self._loop.close()

        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()
        time.sleep(0.5)

    async def _run(self) -> None:
        """Main coroutine that runs all client tasks."""
        tasks = [
            asyncio.create_task(self._connect()),
            asyncio.create_task(self._send_loop()),
            asyncio.create_task(self._heartbeat_loop()),
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

    def stop_async(self) -> None:
        """Stop the client and wait for thread to finish."""
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread:
            self._thread.join(timeout=5)

        if self._ws:
            asyncio.run_coroutine_threadsafe(self._ws.close(), self._loop)


# ============================================================================
# Global Singletons and Utilities
# ============================================================================

_ws_server: Optional[WSBusServer] = None
_ws_client: Optional[WSBusClient] = None


def is_distributed() -> bool:
    """Check if running in distributed mode."""
    return bool(os.environ.get("TUDOU_MASTER_URL"))


def get_ws_server(
    node_id: str = "master",
    host: str = "0.0.0.0",
    port: int = 9900,
    secret: Optional[str] = None
) -> WSBusServer:
    """Get or create the global WebSocket server instance."""
    global _ws_server

    if _ws_server is None:
        _ws_server = WSBusServer(node_id=node_id, host=host, port=port, secret=secret)

    return _ws_server


def get_ws_client(
    node_id: str,
    master_url: Optional[str] = None,
    secret: Optional[str] = None
) -> WSBusClient:
    """Get or create the global WebSocket client instance."""
    global _ws_client

    if _ws_client is None:
        master_url = master_url or os.environ.get("TUDOU_MASTER_URL", WS_MASTER_URL)
        _ws_client = WSBusClient(node_id=node_id, master_url=master_url, secret=secret)

    return _ws_client


def reset_ws_server() -> None:
    """Reset the global server instance (for testing)."""
    global _ws_server
    if _ws_server:
        _ws_server.stop_async()
    _ws_server = None


def reset_ws_client() -> None:
    """Reset the global client instance (for testing)."""
    global _ws_client
    if _ws_client:
        _ws_client.stop_async()
    _ws_client = None
