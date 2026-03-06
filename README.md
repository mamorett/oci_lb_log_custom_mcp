# OCI Load Balancer Log MCP Server

A Model Context Protocol (MCP) server for querying and analyzing Oracle Cloud Infrastructure (OCI) Load Balancer custom logs. This server allows LLMs to directly search through traffic logs by country, IP, location, and perform aggregated traffic analytics.

## Features

- **Search by Country**: Filter logs by country name or ISO country code.
- **Search by IP**: Look up specific IP addresses or CIDR-style prefixes.
- **Geographic Search**: Find traffic originating from specific latitude/longitude bounding boxes.
- **Traffic Analytics**: Get top talkers, country distribution, and protocol statistics.
- **Zero Hardcoding**: Fully configurable via environment variables.

## Prerequisites

1.  **OCI CLI Configured**: You must have a valid OCI configuration file (usually at `~/.oci/config`).
2.  **Environment Variables**: You need the OCIDs for your compartment, log group, and the specific custom log.

## Installation & Usage

### Running via `uvx`

You can run the MCP server directly from GitHub without manual installation using `uvx`:

```bash
export OCI_COMPARTMENT_ID="ocid1.tenancy.oc1..xxxx"
export OCI_LOG_GROUP_ID="ocid1.loggroup.oc1.xxxx"
export OCI_LOG_ID="ocid1.log.oc1.xxxx"

uvx --from git+https://github.com/mamorett/oci_lb_log_custom_mcp.git oci-lb-logs
```

### Configuration for MCP Hosts (e.g., Claude Desktop)

Add the following entry to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "oci-lb-logs": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/mamorett/oci_lb_log_custom_mcp.git",
        "oci-lb-logs"
      ],
      "env": {
        "OCI_COMPARTMENT_ID": "ocid1.tenancy.oc1..your_compartment_ocid",
        "OCI_LOG_GROUP_ID": "ocid1.loggroup.oc1.your_region.your_log_group_ocid",
        "OCI_LOG_ID": "ocid1.log.oc1.your_region.your_custom_log_ocid",
        "OCI_CONFIG_PROFILE": "DEFAULT",
        "OCI_CONFIG_FILE": "/absolute/path/to/your/.oci/config"
      }
    }
  }
}
```

## Tools Exposed

### `search_logs_by_country`
Search logs by country name or country code.
- `country` (string, optional): Full country name (e.g., "United States").
- `country_code` (string, optional): ISO country code (e.g., "US").
- `time_range` (string): Time window to search (e.g., "24h", "7d", "1w"). Default: "24h".
- `limit` (integer): Maximum number of entries to return. Default: 100.

### `search_logs_by_ip`
Search logs by a specific IP address or an IP range prefix.
- `ip_address` (string, optional): Specific IP address.
- `ip_range` (string, optional): IP prefix (e.g., "192.168").
- `time_range` (string): Time window to search. Default: "24h".
- `limit` (integer): Maximum number of entries to return. Default: 100.

### `search_logs_by_location`
Search logs within a geographic bounding box.
- `lat_min`, `lat_max`, `lon_min`, `lon_max` (float): Bounding box coordinates.
- `time_range` (string): Time window to search. Default: "24h".
- `limit` (integer): Maximum number of entries to return. Default: 100.

### `get_traffic_analytics`
Get aggregated traffic statistics and summaries.
- `group_by` (string): Field to aggregate by ("country", "city", "isp", or "protocol"). Default: "country".
- `time_range` (string): Time window to analyze. Default: "24h".
- `limit` (integer): Number of raw log entries to sample for analytics. Default: 1000.

## Environment Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| `OCI_COMPARTMENT_ID` | **Required**. OCID of the OCI Compartment. | N/A |
| `OCI_LOG_GROUP_ID` | **Required**. OCID of the OCI Log Group. | N/A |
| `OCI_LOG_ID` | **Required**. OCID of the OCI Custom Log. | N/A |
| `OCI_CONFIG_PROFILE` | Profile name in your OCI config file. | `DEFAULT` |
| `OCI_CONFIG_FILE` | Path to your OCI config file. | `~/.oci/config` |

## License
MIT
