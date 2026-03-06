import os
import json
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field

import oci
from oci.logging import LoggingManagementClient
from oci.loggingsearch import LogSearchClient
from oci.loggingsearch.models import SearchLogsDetails
from mcp.server.fastmcp import FastMCP

# --- Models ---

class LogEntry(BaseModel):
    timestamp: datetime
    ip: str
    protocol: str
    latitude: float
    longitude: float
    country: str
    country_code: str
    city: str
    isp: str

class AnalyticsResult(BaseModel):
    total_requests: int
    unique_ips: int
    unique_countries: int
    top_items: List[Dict[str, Any]]
    protocol_distribution: Dict[str, int]
    top_isps: List[str]
    time_range: str

class IPSummary(BaseModel):
    ip: str
    request_count: int
    country: str
    country_code: str
    city: str
    isp: str
    protocols: List[str]

class IPsByCountry(BaseModel):
    country: str
    country_code: str
    total_requests: int
    unique_ip_count: int
    ips: List[IPSummary]

# --- Oracle Client ---

class OracleLogsClient:
    def __init__(self):
        """Initialize Oracle Cloud connection from environment variables"""
        self.profile = os.getenv("OCI_CONFIG_PROFILE", "DEFAULT")
        self.config_path = os.path.expanduser(os.getenv("OCI_CONFIG_FILE", "~/.oci/config"))
        
        try:
            # Use Instance Principal if profile isn't found and we're in OCI, otherwise use config file
            if os.path.exists(self.config_path):
                self.config = oci.config.from_file(file_location=self.config_path, profile_name=self.profile)
            else:
                # Fallback to Instance Principal or other auth if needed, 
                # but for this MCP we'll stick to config file as primary.
                raise FileNotFoundError(f"OCI config file not found at {self.config_path}")

            self.logging_client = LoggingManagementClient(self.config)
            self.search_client = LogSearchClient(self.config)
            
            self.compartment_id = os.getenv("OCI_COMPARTMENT_ID")
            self.log_group_id = os.getenv("OCI_LOG_GROUP_ID")
            self.log_id = os.getenv("OCI_LOG_ID")
            
            if not all([self.compartment_id, self.log_group_id, self.log_id]):
                raise ValueError("Missing required OCI environment variables: OCI_COMPARTMENT_ID, OCI_LOG_GROUP_ID, OCI_LOG_ID")
            
        except Exception as e:
            # Print to stderr to avoid breaking MCP protocol
            import sys
            print(f"Error initializing OCI client: {e}", file=sys.stderr)
            raise

    def _build_base_query(self) -> str:
        """Build the base query targeting the specific log"""
        return f'search "{self.compartment_id}/{self.log_group_id}/{self.log_id}"'

    def _parse_time_range(self, time_range: str) -> Tuple[datetime, datetime]:
        """Parse time range string (e.g., '24h', '7d') into datetime objects"""
        now = datetime.utcnow()
        if time_range.endswith('h'):
            delta = timedelta(hours=int(time_range[:-1]))
        elif time_range.endswith('d'):
            delta = timedelta(days=int(time_range[:-1]))
        elif time_range.endswith('w'):
            delta = timedelta(weeks=int(time_range[:-1]))
        else:
            delta = timedelta(hours=24)
        return now - delta, now

    async def execute_query(self, query: str, time_range: str, limit: Optional[int] = None) -> List[Dict]:
        """Execute the OCI Logging search query"""
        start_time, end_time = self._parse_time_range(time_range)
        
        search_details = SearchLogsDetails(
            time_start=start_time,
            time_end=end_time,
            search_query=query,
            is_return_field_info=False
        )

        all_logs = []
        next_page = None

        while True:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: self.search_client.search_logs(search_logs_details=search_details, page=next_page)
            )

            for result in response.data.results:
                try:
                    log_data = json.loads(result.data) if isinstance(result.data, str) else result.data
                    all_logs.append(log_data)
                except (json.JSONDecodeError, TypeError):
                    continue

            next_page = response.headers.get('opc-next-page')
            if not next_page or (limit and len(all_logs) >= limit):
                break

        return all_logs[:limit] if limit else all_logs

    def parse_log_entry(self, oracle_log: Dict) -> Optional[LogEntry]:
        """Parse raw OCI log into LogEntry model"""
        try:
            log_content = oracle_log.get('logContent', {})
            data = log_content.get('data', {})
            timestamp_ms = oracle_log.get('datetime', 0)
            
            return LogEntry(
                timestamp=datetime.fromtimestamp(timestamp_ms / 1000.0),
                ip=data.get('IP', ''),
                protocol=data.get('Protocol', ''),
                latitude=float(data.get('Latitude', 0.0)),
                longitude=float(data.get('Longitude', 0.0)),
                country=data.get('Country', ''),
                country_code=data.get('CountryCode', ''),
                city=data.get('City', ''),
                isp=data.get('ISP', '')
            )
        except Exception:
            return None

# --- MCP Server Setup ---

mcp = FastMCP("OCI Load Balancer Logs")
# Lazy initialization to allow for env vars to be set by the host before client init
client_instance = None

def get_client():
    global client_instance
    if client_instance is None:
        client_instance = OracleLogsClient()
    return client_instance

@mcp.tool()
async def search_logs_by_country(
    country: Optional[str] = None, 
    country_code: Optional[str] = None, 
    time_range: str = "24h", 
    limit: int = 100
) -> List[LogEntry]:
    """Search OCI Load Balancer logs by country or country code."""
    client = get_client()
    query = client._build_base_query()
    conditions = []
    if country: conditions.append(f"data.Country = '{country}'")
    if country_code: conditions.append(f"data.CountryCode = '{country_code}'")
    
    if conditions:
        query += " | where " + " and ".join(conditions)
    
    query += f" | limit {limit}"
    
    raw_logs = await client.execute_query(query, time_range, limit)
    return [e for e in (client.parse_log_entry(l) for l in raw_logs) if e]

@mcp.tool()
async def search_logs_by_ip(
    ip_address: Optional[str] = None, 
    ip_range: Optional[str] = None, 
    time_range: str = "24h", 
    limit: int = 100
) -> List[LogEntry]:
    """Search OCI Load Balancer logs by IP address or IP range (prefix)."""
    client = get_client()
    query = client._build_base_query()
    if ip_address:
        query += f" | where data.IP = '{ip_address}'"
    elif ip_range:
        ip_prefix = ip_range.split('/')[0].rsplit('.', 1)[0]
        query += f" | where data.IP like '{ip_prefix}%'"
    
    query += f" | limit {limit}"
    raw_logs = await client.execute_query(query, time_range, limit)
    return [e for e in (client.parse_log_entry(l) for l in raw_logs) if e]

@mcp.tool()
async def search_logs_by_location(
    lat_min: float, 
    lat_max: float, 
    lon_min: float, 
    lon_max: float, 
    time_range: str = "24h", 
    limit: int = 100
) -> List[LogEntry]:
    """Search OCI Load Balancer logs within geographic bounds."""
    client = get_client()
    query = client._build_base_query()
    query += f" | where data.Latitude >= {lat_min} and data.Latitude <= {lat_max}"
    query += f" | where data.Longitude >= {lon_min} and data.Longitude <= {lon_max}"
    query += f" | limit {limit}"
    
    raw_logs = await client.execute_query(query, time_range, limit)
    return [e for e in (client.parse_log_entry(l) for l in raw_logs) if e]

@mcp.tool()
async def get_traffic_analytics(
    group_by: str = "country", 
    time_range: str = "24h", 
    limit: int = 1000
) -> AnalyticsResult:
    """Get aggregated traffic statistics from OCI Load Balancer logs."""
    from collections import Counter
    client = get_client()
    query = client._build_base_query() + f" | limit {limit}"
    raw_logs = await client.execute_query(query, time_range, limit)
    
    unique_ips = set()
    countries = []
    protocols = []
    isps = []
    grouped_data = []
    
    for log in raw_logs:
        data = log.get('logContent', {}).get('data', {})
        unique_ips.add(data.get('IP', ''))
        countries.append(data.get('Country', ''))
        protocols.append(data.get('Protocol', ''))
        isps.append(data.get('ISP', ''))
        
        if group_by == 'country':
            grouped_data.append(data.get('Country', 'Unknown'))
        elif group_by == 'city':
            grouped_data.append(f"{data.get('City', 'Unknown')}, {data.get('Country', '')}")
        elif group_by == 'isp':
            grouped_data.append(data.get('ISP', 'Unknown'))
        elif group_by == 'protocol':
            grouped_data.append(data.get('Protocol', 'Unknown'))

    return AnalyticsResult(
        total_requests=len(raw_logs),
        unique_ips=len(unique_ips),
        unique_countries=len(set(countries)),
        top_items=[{"name": k, "count": v} for k, v in Counter(grouped_data).most_common(10)],
        protocol_distribution=dict(Counter(protocols)),
        top_isps=[isp for isp, _ in Counter(isps).most_common(5)],
        time_range=time_range
    )

@mcp.tool()
async def list_unique_ips(
    time_range: str = "24h",
    limit: int = 500,
    country: Optional[str] = None,
    country_code: Optional[str] = None,
) -> List[IPSummary]:
    """List all unique IP addresses seen in the logs with their request count, country, city, ISP and protocols.
    Optionally filter by country name or country code."""
    from collections import defaultdict
    client = get_client()
    query = client._build_base_query()
    conditions = []
    if country:
        conditions.append(f"data.Country = '{country}'")
    if country_code:
        conditions.append(f"data.CountryCode = '{country_code}'")
    if conditions:
        query += " | where " + " and ".join(conditions)
    query += f" | limit {limit}"

    raw_logs = await client.execute_query(query, time_range, limit)

    ip_map: Dict[str, dict] = defaultdict(lambda: {
        "request_count": 0,
        "country": "",
        "country_code": "",
        "city": "",
        "isp": "",
        "protocols": set(),
    })

    for log in raw_logs:
        data = log.get("logContent", {}).get("data", {})
        ip = data.get("IP", "")
        if not ip:
            continue
        rec = ip_map[ip]
        rec["request_count"] += 1
        rec["country"] = data.get("Country", rec["country"])
        rec["country_code"] = data.get("CountryCode", rec["country_code"])
        rec["city"] = data.get("City", rec["city"])
        rec["isp"] = data.get("ISP", rec["isp"])
        proto = data.get("Protocol", "")
        if proto:
            rec["protocols"].add(proto)

    results = [
        IPSummary(
            ip=ip,
            request_count=v["request_count"],
            country=v["country"],
            country_code=v["country_code"],
            city=v["city"],
            isp=v["isp"],
            protocols=sorted(v["protocols"]),
        )
        for ip, v in ip_map.items()
    ]
    results.sort(key=lambda x: x.request_count, reverse=True)
    return results


@mcp.tool()
async def get_top_ips(
    time_range: str = "24h",
    top_n: int = 20,
    sample_limit: int = 5000,
) -> List[IPSummary]:
    """Return the top N IP addresses ranked by request count over the given time range."""
    from collections import defaultdict
    client = get_client()
    query = client._build_base_query() + f" | limit {sample_limit}"
    raw_logs = await client.execute_query(query, time_range, sample_limit)

    ip_map: Dict[str, dict] = defaultdict(lambda: {
        "request_count": 0,
        "country": "",
        "country_code": "",
        "city": "",
        "isp": "",
        "protocols": set(),
    })

    for log in raw_logs:
        data = log.get("logContent", {}).get("data", {})
        ip = data.get("IP", "")
        if not ip:
            continue
        rec = ip_map[ip]
        rec["request_count"] += 1
        rec["country"] = data.get("Country", rec["country"])
        rec["country_code"] = data.get("CountryCode", rec["country_code"])
        rec["city"] = data.get("City", rec["city"])
        rec["isp"] = data.get("ISP", rec["isp"])
        proto = data.get("Protocol", "")
        if proto:
            rec["protocols"].add(proto)

    results = sorted(
        [
            IPSummary(
                ip=ip,
                request_count=v["request_count"],
                country=v["country"],
                country_code=v["country_code"],
                city=v["city"],
                isp=v["isp"],
                protocols=sorted(v["protocols"]),
            )
            for ip, v in ip_map.items()
        ],
        key=lambda x: x.request_count,
        reverse=True,
    )
    return results[:top_n]


@mcp.tool()
async def get_ips_by_country(
    time_range: str = "24h",
    limit: int = 2000,
) -> List[IPsByCountry]:
    """Return unique IP addresses grouped by country, with per-country totals.
    Useful for understanding which countries have the most unique sources."""
    from collections import defaultdict
    client = get_client()
    query = client._build_base_query() + f" | limit {limit}"
    raw_logs = await client.execute_query(query, time_range, limit)

    # country_code -> {country, country_code, ips: {ip -> IPSummary-like dict}}
    country_map: Dict[str, dict] = defaultdict(lambda: {
        "country": "",
        "country_code": "",
        "total_requests": 0,
        "ip_data": defaultdict(lambda: {
            "request_count": 0,
            "city": "",
            "isp": "",
            "protocols": set(),
        }),
    })

    for log in raw_logs:
        data = log.get("logContent", {}).get("data", {})
        ip = data.get("IP", "")
        cc = data.get("CountryCode", "")
        if not ip or not cc:
            continue
        crec = country_map[cc]
        crec["country"] = data.get("Country", crec["country"])
        crec["country_code"] = cc
        crec["total_requests"] += 1
        irec = crec["ip_data"][ip]
        irec["request_count"] += 1
        irec["city"] = data.get("City", irec["city"])
        irec["isp"] = data.get("ISP", irec["isp"])
        proto = data.get("Protocol", "")
        if proto:
            irec["protocols"].add(proto)

    results = []
    for cc, crec in country_map.items():
        ip_summaries = sorted(
            [
                IPSummary(
                    ip=ip,
                    request_count=irec["request_count"],
                    country=crec["country"],
                    country_code=crec["country_code"],
                    city=irec["city"],
                    isp=irec["isp"],
                    protocols=sorted(irec["protocols"]),
                )
                for ip, irec in crec["ip_data"].items()
            ],
            key=lambda x: x.request_count,
            reverse=True,
        )
        results.append(
            IPsByCountry(
                country=crec["country"],
                country_code=crec["country_code"],
                total_requests=crec["total_requests"],
                unique_ip_count=len(ip_summaries),
                ips=ip_summaries,
            )
        )
    results.sort(key=lambda x: x.total_requests, reverse=True)
    return results


def main():
    mcp.run()

if __name__ == "__main__":
    main()
