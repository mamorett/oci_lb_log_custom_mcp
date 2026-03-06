# OCI Load Balancer Log MCP Server - Rewrite Plan

## Goal
Complete rewrite of the existing Streamlit/LangChain codebase into a single-file, fully parameterizable MCP (Model Context Protocol) server using the `FastMCP` framework.

## Architecture
- **Framework:** `FastMCP` (from `mcp.server.fastmcp`).
- **Single-File:** All logic consolidated in `mcp_server.py`.
- **Zero Hardcoding:** All OCI identifiers and configurations must come from environment variables.
- **Dependencies:** Remove `streamlit`, `langchain`, `langgraph`, and `langchain_google_genai`.

## Implementation Details

### 1. Environment Variables
The server will require the following environment variables:
- `OCI_CONFIG_PROFILE`: OCI profile name (e.g., `DEFAULT`).
- `OCI_COMPARTMENT_ID`: OCID of the compartment.
- `OCI_LOG_GROUP_ID`: OCID of the log group.
- `OCI_LOG_ID`: OCID of the custom log.
- `OCI_CONFIG_FILE`: (Optional) Path to OCI config file.

### 2. Core Components (in `mcp_server.py`)
- **Models:** Pydantic models for `LogEntry` and tool parameters.
- **Oracle Client:** Refactored `OracleLogsClient` class that:
    - Initializes from environment variables.
    - Builds OCI Logging Search queries.
    - Handles pagination and JSON parsing of results.
- **MCP Tools:**
    - `search_logs_by_country(country, country_code, time_range, limit)`
    - `search_logs_by_ip(ip_address, ip_range, time_range, limit)`
    - `search_logs_by_location(lat_min, lat_max, lon_min, lon_max, time_range, limit)`
    - `get_traffic_analytics(group_by, time_range, limit)`

### 3. Execution Steps
1. Update `requirements.txt`.
2. Create `.env.example`.
3. Implement the `mcp_server.py`.
4. Verify the server with `mcp dev`.
