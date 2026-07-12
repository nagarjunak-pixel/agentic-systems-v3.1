import os
import json
import pytest
import shutil
import tempfile
from typing import Dict, Any

from core.memory.engine import MemoryEngine
from core.orchestrator.broker import TemporalEventBroker
from wmg.vault import CredentialVault, AccessDeniedError
from wmg.gateway import WebhookMessagingGateway, PlatformAdapter, SlackAdapter, TeamsAdapter, WhatsAppAdapter
from wmg.api import AINativeAPI
from abtm.budget import BudgetManager
from abtm.runaway import RunawayGuard

@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)

@pytest.fixture
def memory_engine(temp_dir):
    engine = MemoryEngine(temp_dir)
    yield engine
    engine.shutdown()

@pytest.fixture
def credential_vault():
    secrets = {
        "slack": {"token": "xoxb-slack-secret-token"},
        "teams": {"webhook_url": "https://outlook.office.com/webhook/teams-secret"},
        "whatsapp": {"token": "eaag-whatsapp-secret-token"}
    }
    vault = CredentialVault(secrets)
    return vault

def test_credential_isolation(credential_vault):
    # Register the PlatformAdapter class
    credential_vault.register_allowed_class(PlatformAdapter)
    
    # Create an authorized class instance
    class AuthorizedAdapter(PlatformAdapter):
        pass
        
    auth_adapter = AuthorizedAdapter("slack", credential_vault)
    
    # Retrieve credential using authorized adapter - should succeed
    creds = credential_vault.get_credentials(auth_adapter, "slack")
    assert creds["token"] == "xoxb-slack-secret-token"
    
    # Create an unauthorized class
    class UnauthorizedClass:
        pass
        
    unauth_obj = UnauthorizedClass()
    
    # Verify that requesting credentials throws AccessDeniedError
    with pytest.raises(AccessDeniedError) as exc_info:
        credential_vault.get_credentials(unauth_obj, "slack")
    assert "Security Violation: Access to credentials" in str(exc_info.value)

def test_unknown_platform_rejected(credential_vault, memory_engine):
    gateway = WebhookMessagingGateway(vault=credential_vault, memory_engine=memory_engine)
    
    with pytest.raises(ValueError) as exc_info:
        gateway.establish_connection("conn_1", "discord", 100)
    assert "Unknown platform 'discord'" in str(exc_info.value)

def test_slack_roundtrip(credential_vault, memory_engine):
    gateway = WebhookMessagingGateway(vault=credential_vault, memory_engine=memory_engine)
    
    # Slack connection
    gateway.establish_connection("conn_slack", "slack", 100)
    
    # Webhook simulation
    slack_payload = {
        "event": {
            "user": "U12345",
            "text": "Hello World from Slack",
            "channel": "C12345",
            "ts": "1625243121.000200"
        }
    }
    
    res_in = gateway.receive_incoming_message("conn_slack", slack_payload)
    assert res_in["normalized_message"]["sender"] == "U12345"
    assert res_in["normalized_message"]["text"] == "Hello World from Slack"
    assert res_in["tokens_consumed"] == len("Hello World from Slack") // 4
    
    # Outgoing dispatch
    res_out = gateway.dispatch_outgoing_message("conn_slack", "U12345", "Response to Slack")
    assert res_out["success"] is True
    assert res_out["recipient"] == "U12345"
    assert res_out["tokens_consumed"] == len("Response to Slack") // 4

def test_teams_roundtrip(credential_vault, memory_engine):
    gateway = WebhookMessagingGateway(vault=credential_vault, memory_engine=memory_engine)
    gateway.establish_connection("conn_teams", "teams", 100)
    
    teams_payload = {
        "from": {"id": "usr-teams-1"},
        "text": "Hello Teams",
        "conversation": {"id": "channel-teams-2"},
        "timestamp": "2026-07-13T00:00:00Z"
    }
    
    res_in = gateway.receive_incoming_message("conn_teams", teams_payload)
    assert res_in["normalized_message"]["sender"] == "usr-teams-1"
    assert res_in["normalized_message"]["text"] == "Hello Teams"
    
    res_out = gateway.dispatch_outgoing_message("conn_teams", "usr-teams-1", "Reply to Teams")
    assert res_out["success"] is True

def test_whatsapp_roundtrip(credential_vault, memory_engine):
    gateway = WebhookMessagingGateway(vault=credential_vault, memory_engine=memory_engine)
    gateway.establish_connection("conn_wa", "whatsapp", 100)
    
    whatsapp_payload = {
        "messages": [
            {
                "from": "1234567890",
                "text": {"body": "Hello WhatsApp"},
                "timestamp": "1625243121"
            }
        ]
    }
    
    res_in = gateway.receive_incoming_message("conn_wa", whatsapp_payload)
    assert res_in["normalized_message"]["sender"] == "1234567890"
    assert res_in["normalized_message"]["text"] == "Hello WhatsApp"
    
    res_out = gateway.dispatch_outgoing_message("conn_wa", "1234567890", "Reply WhatsApp")
    assert res_out["success"] is True

def test_connection_token_limit_termination(credential_vault, memory_engine):
    # Set a tiny token limit of 5 tokens
    gateway = WebhookMessagingGateway(vault=credential_vault, memory_engine=memory_engine)
    gateway.establish_connection("conn_limited", "slack", 5)
    
    # 1. First outgoing message consumes len("Hello") // 4 = 1 token
    gateway.dispatch_outgoing_message("conn_limited", "U1", "Hello")
    
    # 2. Second outgoing message consumes len("This is a long message") // 4 = 5 tokens (total 6 > 5 limit)
    with pytest.raises(RuntimeError) as exc_info:
        gateway.dispatch_outgoing_message("conn_limited", "U1", "This is a long message")
    assert "Rate limit exceeded on connection" in str(exc_info.value)
    
    # Verify connection status is TERMINATED
    conn = gateway.connections["conn_limited"]
    assert conn.status == "TERMINATED"
    
    # Verify that further incoming messages are rejected
    slack_payload = {
        "event": {
            "user": "U12345",
            "text": "Hello again",
            "channel": "C12345",
            "ts": "1625243121.000200"
        }
    }
    with pytest.raises(RuntimeError) as exc_info_incoming:
        gateway.receive_incoming_message("conn_limited", slack_payload)
    assert "has been terminated" in str(exc_info_incoming.value)

def test_ai_native_api(credential_vault, memory_engine):
    # Setup dependencies
    broker = TemporalEventBroker()
    try:
        budget_manager = BudgetManager(global_limit=1000, memory_engine=memory_engine)
        runaway_guard = RunawayGuard(broker, check_interval_seconds=1.0)
        gateway = WebhookMessagingGateway(vault=credential_vault, memory_engine=memory_engine)
        
        # Write routing_config file
        wammr_config = {
            "routing_matrix": {
                "code_gen": {
                    "primary_model": "gpt-4o",
                    "fallback_model": "claude-3",
                    "timeout_ms": 5000,
                    "max_retries": 1
                }
            },
            "circuit_breakers": {
                "failure_threshold_pct": 50,
                "recovery_time_seconds": 30,
                "health_check_interval_seconds": 10
            }
        }
        config_path = os.path.join(memory_engine.root_dir, "routing_config.json")
        with open(config_path, "w") as f:
            json.dump(wammr_config, f)
        
        # Note: ModelRouter uses requests, so let's mock the provider override
        from core.wammr.router import ModelRouter
        router = ModelRouter(config_path)
        router.client_override = lambda model, prompt, timeout: f"Mock Response from {model}"
        
        api = AINativeAPI(budget_manager, runaway_guard, gateway, router)
        
        # 1. Test GET /api/v1/agent/status
        res_status = api.handle_request("/api/v1/agent/status", "GET")
        assert res_status["status"] == "success"
        assert "active_agents" in res_status
        
        # 2. Test GET /api/v1/metrics/summary
        res_metrics = api.handle_request("/api/v1/metrics/summary", "GET")
        assert res_metrics["status"] == "success"
        assert "global_tokens_consumed" in res_metrics
        
        # 3. Test POST /api/v1/agent/query
        query_payload = {
            "agent_id": "agent_expert",
            "task_type": "code_gen",
            "prompt": "Write bubble sort"
        }
        res_query = api.handle_request("/api/v1/agent/query", "POST", query_payload)
        assert res_query["status"] == "completed"
        assert res_query["result"] == "Mock Response from gpt-4o"
        assert res_query["routing_metadata"]["task_type"] == "code_gen"
        
        # 4. Test Semantic query failure
        invalid_query = {
            "agent_id": "agent_expert",
            "task_type": "code_gen"
            # missing prompt
        }
        res_invalid = api.handle_request("/api/v1/agent/query", "POST", invalid_query)
        assert "validation failed" in res_invalid["error"].lower()
    finally:
        # Clean up background services
        broker.shutdown()
