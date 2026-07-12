import os
import json
import logging
from typing import Dict, Any, List, Optional
from .vault import CredentialVault

logger = logging.getLogger("WMG.Gateway")

class PlatformAdapter:
    def __init__(self, platform_name: str, vault: CredentialVault):
        self.platform_name = platform_name
        self.vault = vault

    def send_message(self, recipient: str, message: str) -> Dict[str, Any]:
        creds = self.vault.get_credentials(self, self.platform_name)
        # Mock network dispatch using credentials
        token = creds.get("token") or creds.get("webhook_url")
        logger.info(f"[{self.platform_name}] Sent message to {recipient} using token: {token[:8]}...")
        return {
            "platform": self.platform_name,
            "recipient": recipient,
            "success": True,
            "status": "delivered"
        }

    def handle_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

class SlackAdapter(PlatformAdapter):
    def __init__(self, vault: CredentialVault):
        super().__init__("slack", vault)

    def handle_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Validate Slack format
        if "event" not in payload:
            raise ValueError("Invalid Slack webhook payload")
        event = payload["event"]
        return {
            "sender": event.get("user"),
            "text": event.get("text"),
            "channel": event.get("channel"),
            "timestamp": event.get("ts")
        }

class TeamsAdapter(PlatformAdapter):
    def __init__(self, vault: CredentialVault):
        super().__init__("teams", vault)

    def handle_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Validate Teams format
        if "from" not in payload or "text" not in payload:
            raise ValueError("Invalid Teams webhook payload")
        return {
            "sender": payload["from"].get("id"),
            "text": payload["text"],
            "channel": payload.get("conversation", {}).get("id"),
            "timestamp": payload.get("timestamp")
        }

class WhatsAppAdapter(PlatformAdapter):
    def __init__(self, vault: CredentialVault):
        super().__init__("whatsapp", vault)

    def handle_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Validate WhatsApp format
        if "messages" not in payload:
            raise ValueError("Invalid WhatsApp webhook payload")
        msg = payload["messages"][0]
        return {
            "sender": msg.get("from"),
            "text": msg.get("text", {}).get("body"),
            "channel": msg.get("from"),
            "timestamp": msg.get("timestamp")
        }

class ConnectionState:
    def __init__(self, connection_id: str, platform: str, token_limit: int):
        self.connection_id = connection_id
        self.platform = platform
        self.token_limit = token_limit
        self.tokens_used = 0
        self.status = "CONNECTED"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "connection_id": self.connection_id,
            "platform": self.platform,
            "token_limit": self.token_limit,
            "tokens_used": self.tokens_used,
            "status": self.status
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConnectionState":
        state = cls(data["connection_id"], data["platform"], data["token_limit"])
        state.tokens_used = data["tokens_used"]
        state.status = data["status"]
        return state

class WebhookMessagingGateway:
    def __init__(self, vault: CredentialVault, memory_engine: Any = None, state_file: str = "wmg/gateway_state.json"):
        self.vault = vault
        self.memory_engine = memory_engine
        self.state_file = state_file
        
        self.adapters: Dict[str, PlatformAdapter] = {}
        self.connections: Dict[str, ConnectionState] = {}
        
        # Register standard adapters
        self.register_adapter("slack", SlackAdapter(self.vault))
        self.register_adapter("teams", TeamsAdapter(self.vault))
        self.register_adapter("whatsapp", WhatsAppAdapter(self.vault))
        
        # Register the base and specific adapter classes in the vault
        self.vault.register_allowed_class(PlatformAdapter)
        self.vault.register_allowed_class(SlackAdapter)
        self.vault.register_allowed_class(TeamsAdapter)
        self.vault.register_allowed_class(WhatsAppAdapter)
        
        # Load persisted connection states
        self._load_state()

    def register_adapter(self, name: str, adapter: PlatformAdapter):
        self.adapters[name] = adapter
        logger.info(f"Registered gateway adapter: {name}")

    def _load_state(self):
        if not self.memory_engine:
            return
        
        full_path = os.path.join(self.memory_engine.root_dir, self.state_file)
        if os.path.exists(full_path):
            try:
                with open(full_path, "r") as f:
                    data = json.load(f)
                for conn_id, conn_data in data.get("connections", {}).items():
                    self.connections[conn_id] = ConnectionState.from_dict(conn_data)
                logger.info(f"Loaded {len(self.connections)} connection states")
            except Exception as e:
                logger.error(f"Failed to load WMG state: {e}")

    def _save_state(self):
        if not self.memory_engine:
            return
        
        state_data = {
            "connections": {conn_id: conn.to_dict() for conn_id, conn in self.connections.items()}
        }
        try:
            self.memory_engine.write_file_sync(self.state_file, json.dumps(state_data, indent=2))
        except Exception as e:
            logger.error(f"Failed to save WMG state: {e}")

    def establish_connection(self, connection_id: str, platform: str, token_limit: int) -> ConnectionState:
        if platform not in self.adapters:
            raise ValueError(f"Unknown platform '{platform}'. No adapter registered.")
            
        conn = ConnectionState(connection_id, platform, token_limit)
        self.connections[connection_id] = conn
        self._save_state()
        logger.info(f"Connection established: id={connection_id}, platform={platform}, limit={token_limit}")
        return conn

    def receive_incoming_message(self, connection_id: str, raw_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Receives an incoming webhook/message.
        Validates token limits and platform support, processes content,
        updates token limits, and persists connection state.
        """
        conn = self.connections.get(connection_id)
        if not conn:
            raise ValueError(f"Connection ID '{connection_id}' not found.")
            
        if conn.status == "TERMINATED":
            raise RuntimeError(f"Connection '{connection_id}' has been terminated.")
            
        adapter = self.adapters.get(conn.platform)
        if not adapter:
            raise RuntimeError(f"Adapter for platform '{conn.platform}' is missing.")
            
        # Parse payload
        normalized = adapter.handle_webhook(raw_payload)
        
        # Estimate token cost: 1 token per 4 chars of text
        text_len = len(normalized.get("text") or "")
        est_tokens = max(1, text_len // 4)
        
        # Active token limit check
        if conn.tokens_used + est_tokens > conn.token_limit:
            conn.status = "TERMINATED"
            self._save_state()
            raise RuntimeError(
                f"Rate limit exceeded on connection '{connection_id}': "
                f"used={conn.tokens_used}, requested={est_tokens}, limit={conn.token_limit}. "
                "Connection terminated."
            )
            
        # Update usage
        conn.tokens_used += est_tokens
        self._save_state()
        
        return {
            "normalized_message": normalized,
            "connection_id": connection_id,
            "tokens_consumed": est_tokens
        }

    def dispatch_outgoing_message(self, connection_id: str, recipient: str, message_text: str) -> Dict[str, Any]:
        """
        Dispatches an outgoing message.
        Validates token limits, executes send via adapter, and records tokens.
        """
        conn = self.connections.get(connection_id)
        if not conn:
            raise ValueError(f"Connection ID '{connection_id}' not found.")
            
        if conn.status == "TERMINATED":
            raise RuntimeError(f"Connection '{connection_id}' has been terminated.")
            
        adapter = self.adapters.get(conn.platform)
        if not adapter:
            raise RuntimeError(f"Adapter for platform '{conn.platform}' is missing.")
            
        # Estimate token cost
        est_tokens = max(1, len(message_text) // 4)
        
        # Active token limit check
        if conn.tokens_used + est_tokens > conn.token_limit:
            conn.status = "TERMINATED"
            self._save_state()
            raise RuntimeError(
                f"Rate limit exceeded on connection '{connection_id}': "
                f"used={conn.tokens_used}, requested={est_tokens}, limit={conn.token_limit}. "
                "Connection terminated."
            )
            
        # Dispatch via platform adapter (which gets isolated secrets from vault)
        res = adapter.send_message(recipient, message_text)
        
        # Update usage
        conn.tokens_used += est_tokens
        self._save_state()
        
        res["tokens_consumed"] = est_tokens
        return res
