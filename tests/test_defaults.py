"""
Tests for app.defaults — ensures all centralized constants exist and
have reasonable types/values.
"""
from app.defaults import (
    # Network
    PORTAL_PORT, WEB_PORT, AGENT_PORT, WS_BUS_PORT,
    BIND_ADDRESS, CORS_ORIGINS_DEFAULT,
    IP_DETECT_TARGET, IP_DETECT_PORT, LOCAL_ADDRESSES,
    # URLs
    OLLAMA_URL, OPENAI_BASE_URL, UNSLOTH_BASE_URL, WS_MASTER_URL,
    # LLM
    DEFAULT_PROVIDER, DEFAULT_MODEL, DEFAULT_EMBEDDING_MODEL, SKILLFORGE_MODEL,
    # Timeouts
    APPROVAL_TIMEOUT, DELEGATION_TIMEOUT, TASK_EXECUTION_TIMEOUT,
    WORKFLOW_TIMEOUT, HTTP_REQUEST_TIMEOUT, SQLITE_CONNECT_TIMEOUT,
    WS_PING_TIMEOUT, WS_ACK_TIMEOUT,
    # Retry
    LLM_MAX_RETRIES, LLM_BACKOFF_FACTOR, LLM_POOL_CONNECTIONS, LLM_POOL_MAXSIZE,
    MAX_PARALLEL_WORKERS, MAX_TASK_DEPTH, MAX_TASK_RETAINED,
    MAX_DELEGATION_CONCURRENCY, MAX_DELEGATION_QUEUE,
    # Size limits
    MAX_CONTENT_UPLOAD, MAX_DATA_UPLOAD, MAX_FILE_SERVE,
    MAX_JSON_FRAME, MAX_HASH_BYTES, HASH_CHUNK_SIZE, LOG_MAX_MB,
    # Char limits
    MAX_SKILL_RESULT_CHARS, MAX_JSON_RESULT_CHARS,
    MAX_TOOL_RESULT_CHARS, MAX_HTTP_RESPONSE_CHARS, CONTENT_PREVIEW_CHARS,
    # Session / retention
    SESSION_TTL, RATE_LIMIT_RPS, RATE_LIMIT_BURST,
    AUDIT_LOG_MAX_BUFFER, AUDIT_LOG_RETENTION,
    MAX_CHANGELOG_SIZE, EVENT_HISTORY_SIZE, MESSAGE_LOAD_LIMIT,
    # Scan
    SCAN_MAX_DEPTH, SCAN_MAX_FILES, PROJECT_SCAN_MAX_FILES,
    # Thresholds
    BUDGET_WARNING_THRESHOLD, BUDGET_ATTENTION_THRESHOLD,
    CONTEXT_WARN_HIGH, CONTEXT_WARN_MEDIUM, CONTEXT_WARN_LOW,
)


class TestNetworkDefaults:
    def test_ports_are_ints(self):
        for port in (PORTAL_PORT, WEB_PORT, AGENT_PORT, WS_BUS_PORT, IP_DETECT_PORT):
            assert isinstance(port, int)
            assert 1 <= port <= 65535

    def test_bind_address(self):
        assert isinstance(BIND_ADDRESS, str)

    def test_cors_origins(self):
        origins = CORS_ORIGINS_DEFAULT.split(",")
        assert len(origins) >= 2
        for o in origins:
            assert o.startswith("http")

    def test_local_addresses(self):
        assert "127.0.0.1" in LOCAL_ADDRESSES
        assert "localhost" in LOCAL_ADDRESSES


class TestURLDefaults:
    def test_urls_are_strings(self):
        for url in (OLLAMA_URL, OPENAI_BASE_URL, UNSLOTH_BASE_URL, WS_MASTER_URL):
            assert isinstance(url, str)
            assert "://" in url

    def test_ws_url_uses_ws_protocol(self):
        assert WS_MASTER_URL.startswith("ws://")


class TestLLMDefaults:
    def test_provider_is_string(self):
        assert isinstance(DEFAULT_PROVIDER, str)
        assert len(DEFAULT_PROVIDER) > 0

    def test_model_is_string(self):
        assert isinstance(DEFAULT_MODEL, str)

    def test_embedding_model(self):
        assert isinstance(DEFAULT_EMBEDDING_MODEL, str)


class TestTimeoutDefaults:
    def test_timeouts_are_positive(self):
        for t in (APPROVAL_TIMEOUT, DELEGATION_TIMEOUT, TASK_EXECUTION_TIMEOUT,
                  WORKFLOW_TIMEOUT, HTTP_REQUEST_TIMEOUT, SQLITE_CONNECT_TIMEOUT,
                  WS_PING_TIMEOUT, WS_ACK_TIMEOUT):
            assert t > 0


class TestSizeLimits:
    def test_upload_limits_ordered(self):
        assert MAX_CONTENT_UPLOAD < MAX_DATA_UPLOAD < MAX_FILE_SERVE

    def test_limits_are_positive(self):
        for sz in (MAX_CONTENT_UPLOAD, MAX_DATA_UPLOAD, MAX_FILE_SERVE,
                   MAX_JSON_FRAME, MAX_HASH_BYTES, HASH_CHUNK_SIZE):
            assert sz > 0

    def test_char_limits_positive(self):
        for c in (MAX_SKILL_RESULT_CHARS, MAX_JSON_RESULT_CHARS,
                  MAX_TOOL_RESULT_CHARS, MAX_HTTP_RESPONSE_CHARS,
                  CONTENT_PREVIEW_CHARS):
            assert c > 0


class TestRetentionDefaults:
    def test_session_ttl_is_one_day(self):
        assert SESSION_TTL == 86400

    def test_rate_limits_positive(self):
        assert RATE_LIMIT_RPS > 0
        assert RATE_LIMIT_BURST > RATE_LIMIT_RPS


class TestThresholds:
    def test_budget_thresholds_in_range(self):
        assert 0 < BUDGET_WARNING_THRESHOLD < BUDGET_ATTENTION_THRESHOLD <= 1.0

    def test_context_warn_ordered(self):
        assert CONTEXT_WARN_LOW < CONTEXT_WARN_MEDIUM < CONTEXT_WARN_HIGH <= 1.0


class TestRetryDefaults:
    def test_retry_count_positive(self):
        assert LLM_MAX_RETRIES > 0

    def test_pool_sizes(self):
        assert LLM_POOL_CONNECTIONS > 0
        assert LLM_POOL_MAXSIZE >= LLM_POOL_CONNECTIONS

    def test_backoff_positive(self):
        assert LLM_BACKOFF_FACTOR > 0


class TestScanDefaults:
    def test_scan_limits(self):
        assert SCAN_MAX_DEPTH > 0
        assert SCAN_MAX_FILES > 0
        assert PROJECT_SCAN_MAX_FILES >= SCAN_MAX_FILES
