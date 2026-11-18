"""Synthetic incidents for testing search properly.

10 scenarios x 10 incidents, each written with different wording, so a search can
be checked against a known answer: "payments failing after deploy" should bring
back the database-pool incidents, not the cache ones. Everything is deterministic
(fixed ids and dates), so seeding twice never creates duplicates.
"""

import datetime
import uuid

from app.api.dto.incident import Incident, IncidentStatus, Severity

UTC = datetime.timezone.utc
SEED_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "opsmind-seed-incidents")
SEED_TAG = "seed"
SCENARIO_TAG_PREFIX = "scenario:"
BASE_DATE = datetime.datetime(2026, 9, 1, 8, 0, tzinfo=UTC)

SCENARIOS = [
    {
        "key": "db-pool",
        "services": ["payment-service", "checkout-service", "order-service"],
        "root_cause": "The database connection pool was exhausted by a connection leak in the new release.",
        "resolution": "Increased the pool size, fixed the leaked connections and restarted the service.",
        "variants": [
            ("Checkout returning 503 after the evening deploy", "Customers see HTTP 503 at checkout since the 18:00 release. Application logs show timeouts waiting for a database connection."),
            ("Payment API timeouts", "Payment requests hang for 30 seconds and then fail. Database dashboards show all connections in use."),
            ("Orders not saving, users see error page", "Order submission fails with 'could not obtain connection from pool'. It started right after a traffic spike."),
            ("Latency spike and 5xx on the orders endpoint", "p99 latency jumped from 200 ms to 25 s and the error rate hit 40 percent. Database CPU is low, but the connection count is at its limit."),
            ("Service unavailable errors during peak hour", "Health checks fail intermittently during the lunch peak. Threads are blocked waiting for database connections."),
            ("Intermittent 503s, restarts help for a while", "Restarting the pods fixes it for roughly an hour, then errors return. We suspect a leak holding connections open."),
            ("Too many connections error from Postgres", "Postgres rejects new clients with 'sorry, too many clients already'. Several services share the same database."),
            ("Users cannot complete purchases", "The purchase flow is stuck on the final step. Backend logs show connection acquisition timeouts after the release."),
            ("API gateway reports upstream timeout for payments", "The gateway returns 504 for payments. The payments service is up, but requests queue behind exhausted database connections."),
            ("Database connections maxed out after config change", "After a config rollout reduced the pool size, the service ran out of database connections under normal load."),
        ],
    },
    {
        "key": "disk-full",
        "services": ["batch-service", "log-service", "reporting-service"],
        "root_cause": "Log files grew without limit because rotation was disabled in the last config change.",
        "resolution": "Freed space by compressing and deleting old logs, and re-enabled log rotation.",
        "variants": [
            ("No space left on device on batch server", "Nightly batch jobs fail with 'No space left on device'. The root volume shows 100 percent usage."),
            ("Log volume at 100 percent", "Alerting fired because the log volume is full. New log lines are being dropped."),
            ("Reports failing to generate, cannot write temp files", "Report generation crashes while writing temporary files. The disk on the reporting host is full."),
            ("Application crashes writing to disk", "The service exits on startup with an I/O error. df shows the data partition completely used."),
            ("Database cannot write WAL, disk alert escalated", "Postgres stopped accepting writes because the WAL directory ran out of space."),
            ("Uploads failing with 500", "File uploads return 500. The upload directory sits on a full disk."),
            ("Host unresponsive, inodes exhausted", "New files cannot be created although there seems to be free space. Inode usage is at 100 percent from millions of tiny files."),
            ("Container evicted due to ephemeral storage pressure", "Pods are being evicted by the node because ephemeral storage is almost full."),
            ("Backups failing: target volume has no free space", "The nightly backup job aborts because the backup volume cannot hold another archive."),
            ("Logs missing in the dashboard since this morning", "The log pipeline stopped indexing. The log server disk is full and the agent is paused."),
        ],
    },
    {
        "key": "tls-cert",
        "services": ["auth-service", "api-gateway", "web-frontend"],
        "root_cause": "The TLS certificate expired because the automatic renewal job had been failing silently.",
        "resolution": "Issued and installed a new certificate, and fixed the renewal job and its alerting.",
        "variants": [
            ("HTTPS errors on the login page", "Browsers show a certificate warning on the login page. Mobile app logins fail with an SSL error."),
            ("SSL handshake failures since midnight", "Clients cannot connect to the API since 00:00. The handshake fails with a certificate expired message."),
            ("Partners report certificate not valid", "Several partner integrations stopped working and report that our certificate is no longer valid."),
            ("Website shows 'Your connection is not private'", "Customers see a privacy warning when opening the website. The certificate end date has passed."),
            ("Service-to-service calls failing with x509 error", "Internal calls fail with 'x509: certificate has expired or is not yet valid'."),
            ("Mobile app cannot reach the backend", "App users see 'secure connection failed'. The backend works over plain HTTP in tests."),
            ("Webhook deliveries rejected by customers", "Customers say our webhook calls are rejected because the sender certificate is invalid."),
            ("Load balancer serving an old certificate", "The load balancer still presents the previous certificate after renewal. The new certificate was never attached."),
            ("mTLS authentication broke for internal tools", "Internal tools using client certificates are denied. The client certificate expired yesterday."),
            ("Intermittent SSL errors from one region", "Only users in one region see certificate errors. One edge node was never updated with the new certificate."),
        ],
    },
    {
        "key": "cache-down",
        "services": ["catalog-service", "session-service", "search-service"],
        "root_cause": "The Redis primary ran out of memory, evicted keys and then failed over.",
        "resolution": "Increased Redis memory, tuned the eviction policy and key expiry, and warmed the cache.",
        "variants": [
            ("Pages loading very slowly", "Product pages take 10 seconds to load. The cache hit ratio dropped to almost zero."),
            ("Redis unreachable from the catalog service", "The catalog service logs connection refused to Redis and falls back to the database, which is now overloaded."),
            ("Sessions lost, users logged out repeatedly", "Users are logged out every few minutes. The session store shows evicted keys."),
            ("Search results stale after cache outage", "Search shows outdated prices. The cache cluster restarted and refilled with old data."),
            ("High database load after cache failure", "Database CPU is at 95 percent. Cache misses send every request to the database."),
            ("Intermittent 503s on product API when cache fails over", "Brief 503 bursts every time the Redis primary fails over. Clients do not retry."),
            ("Redis latency spikes up to 2 seconds", "Slow commands are reported on the Redis cluster. Memory usage is at 100 percent and keys are being evicted."),
            ("Cache cluster out of memory", "Redis hit maxmemory and rejects writes with OOM errors."),
            ("Rate limiter not working, counters reset", "Request counters disappeared after a Redis restart, so rate limits were not enforced for a while."),
            ("Homepage slow, cache warmup not finished", "After the maintenance window the homepage is slow because the cache has not been warmed yet."),
        ],
    },
    {
        "key": "oom",
        "services": ["recommendation-service", "notification-service", "ingest-service"],
        "root_cause": "A memory leak in the new release made containers exceed their memory limit.",
        "resolution": "Rolled back the release, fixed the leak and temporarily raised the memory limit.",
        "variants": [
            ("Pods restarting in a crash loop", "The service keeps restarting. Kubernetes shows OOMKilled as the reason."),
            ("Memory usage grows steadily until the process dies", "Memory climbs by about 100 MB per hour and the process is killed after roughly six hours."),
            ("Notification delivery delayed, workers keep dying", "Workers exit unexpectedly and the notification backlog grows. Logs end abruptly without an error."),
            ("java.lang.OutOfMemoryError: Java heap space", "Heap dumps show millions of retained objects in a cache that never evicts."),
            ("Ingest workers killed by the kernel", "dmesg shows the OOM killer terminating the ingest process during large file imports."),
            ("Recommendation service slow, long garbage collection pauses", "Response times spike during long GC pauses. The heap is nearly full all the time."),
            ("Container exceeds memory limit after release", "Since version 4.2 the container uses twice the memory it used before and gets killed."),
            ("Node under memory pressure, pods evicted", "A worker node ran out of memory and the scheduler evicted several pods."),
            ("Service becomes unresponsive until restarted", "Requests time out after a few hours of uptime. A restart fixes it temporarily."),
            ("Python worker memory leak when processing images", "Memory grows with every processed image and is never released."),
        ],
    },
    {
        "key": "deploy-regression",
        "services": ["checkout-service", "api-gateway", "user-service"],
        "root_cause": "A faulty release introduced a null pointer bug in the request handler.",
        "resolution": "Rolled back to the previous version and added a regression test before redeploying.",
        "variants": [
            ("500 errors right after the release", "The error rate jumped from 0.1 to 30 percent immediately after version 2.8 was deployed."),
            ("New version breaks user profile endpoint", "The profile endpoint returns 500 for users with no phone number. It worked in the previous version."),
            ("Checkout failing after today's deploy", "Checkout requests fail with an internal server error. The only change since this morning is today's deploy."),
            ("Regression: search filters return empty results", "After the release, filtering by category returns nothing. The previous release worked."),
            ("Rollback required: login broken for SSO users", "SSO login fails with a server error since the release. We rolled back to restore access."),
            ("Unhandled exception spike in logs after deploy", "Logs are flooded with NullPointerException from the new request handler code."),
            ("Mobile clients crash after API change", "A response field was renamed in the latest API version and old mobile clients crash while parsing."),
            ("Canary deployment showing elevated errors", "The canary pods show a 5x error rate compared with the stable version. The deployment was halted."),
            ("Feature flag enabled in production causes errors", "Turning on the new pricing flag caused exceptions in the pricing calculator."),
            ("Database migration in release locked the table", "The release ran a migration that locked a large table, and requests piled up until it finished."),
        ],
    },
    {
        "key": "dns",
        "services": ["api-gateway", "user-service", "billing-service"],
        "root_cause": "The internal DNS resolver was overloaded after a misconfigured retry loop.",
        "resolution": "Scaled the resolver, added caching and fixed the retry loop in the client library.",
        "variants": [
            ("Services cannot resolve each other's hostnames", "Calls between services fail with 'no such host'. Pods can still resolve external names."),
            ("Intermittent name resolution failures", "About 10 percent of lookups time out. Retrying usually works."),
            ("UnknownHostException from the billing service", "Billing logs show UnknownHostException when calling the invoice service."),
            ("DNS lookups taking seconds", "Name resolution latency is over 2 seconds, which slows every outbound call."),
            ("API gateway cannot find upstream service", "The gateway returns 502 because it cannot resolve the upstream hostname."),
            ("Customers cannot reach our domain from some ISPs", "Some users report that our website domain does not resolve for them. Others are fine."),
            ("CoreDNS pods restarting", "CoreDNS keeps crashing and restarting, causing cluster-wide lookup failures."),
            ("Stale DNS record points to the old load balancer", "Traffic still goes to the decommissioned load balancer because the DNS record was not updated."),
            ("DNS change not propagated after migration", "After moving the service, some clients still resolve the old IP address."),
            ("Temporary failure in name resolution inside containers", "Containers report 'temporary failure in name resolution' during peak load."),
        ],
    },
    {
        "key": "queue-backlog",
        "services": ["notification-service", "billing-service", "ingest-service"],
        "root_cause": "Consumers fell behind because a slow downstream call blocked message processing.",
        "resolution": "Scaled up the consumers, added a timeout to the downstream call and drained the backlog.",
        "variants": [
            ("Notification emails delayed by hours", "Customers receive order emails hours late. The notification queue has a growing backlog."),
            ("Kafka consumer lag keeps increasing", "Consumer group lag on the billing topic grew from 1k to 2 million messages."),
            ("Messages stuck in the queue", "The queue depth is constant and nothing is being processed. Consumers appear connected but idle."),
            ("Invoices generated late", "Invoice generation is hours behind. The job queue has hundreds of thousands of pending jobs."),
            ("Dead letter queue filling up", "Thousands of messages landed in the dead letter queue after repeated processing failures."),
            ("Ingest pipeline falling behind", "The ingest pipeline processes events slower than they arrive, and the delay keeps increasing."),
            ("Duplicate notifications sent to customers", "Customers received the same message several times after consumers restarted and reprocessed the queue."),
            ("Consumer group rebalancing constantly", "Consumers keep rebalancing and make no progress. Processing time exceeds the poll interval."),
            ("Worker pool at capacity, jobs timing out", "All workers are busy with long jobs, and new jobs wait for more than an hour."),
            ("Event processing stopped after broker restart", "After a broker restart consumers did not reconnect, so no events were processed."),
        ],
    },
    {
        "key": "upstream",
        "services": ["payment-service", "shipping-service", "signup-service"],
        "root_cause": "The third-party provider was rate limiting us and then partially went down.",
        "resolution": "Enabled retries with backoff, switched traffic to the secondary provider and contacted the vendor.",
        "variants": [
            ("Payments failing with 429 from the provider", "The payment provider returns HTTP 429 Too Many Requests for a large share of charges."),
            ("Third-party API outage affecting checkout", "The provider status page shows an incident. Our checkout cannot authorise cards."),
            ("Shipping label creation failing", "Calls to the carrier API time out, so shipping labels cannot be created."),
            ("External dependency returning 503", "Our upstream partner returns 503 for most requests. Our own service is healthy."),
            ("Rate limit exceeded on vendor API", "We are exceeding the vendor's request quota during the sale and requests are rejected."),
            ("Card payments declined unexpectedly", "A high percentage of card payments are declined with a generic error from the provider."),
            ("Currency conversion service unavailable", "Prices cannot be converted because the exchange rate API is down."),
            ("SMS provider timing out, verification codes not delivered", "Users do not receive verification codes. The SMS vendor API times out."),
            ("Partner API changed response format", "The partner API started returning a different date format and our parser rejects the responses."),
            ("Slow responses from address validation service", "Address validation calls take 20 seconds from the external vendor and slow down signup."),
        ],
    },
    {
        "key": "slow-query",
        "services": ["reporting-service", "order-service", "user-service"],
        "root_cause": "A missing database index caused a full table scan on a large table.",
        "resolution": "Added the missing index, cancelled the long-running queries and reviewed the query plan.",
        "variants": [
            ("Report generation extremely slow", "The monthly report now takes 40 minutes instead of 2. The database is running one heavy query."),
            ("Database CPU at 100 percent", "Primary database CPU is saturated by a single query scanning the orders table."),
            ("Search endpoint latency over 20 seconds", "The orders search page is almost unusable because its query takes more than 20 seconds."),
            ("Slow query log full of the same statement", "The slow query log shows the same SELECT with a sequential scan repeated thousands of times."),
            ("Lock contention, queries waiting", "Many queries are blocked behind a long running transaction that holds locks on the users table."),
            ("Dashboard timeouts after data growth", "Dashboards time out since the events table passed 200 million rows."),
            ("Replica lagging behind the primary", "The read replica is 20 minutes behind because of a heavy analytical query."),
            ("Query plan changed and made the API slow", "After statistics were refreshed the planner picked a bad plan, and a simple lookup now takes seconds."),
            ("N+1 queries causing slow list endpoint", "The list endpoint fires hundreds of small queries per request, and response time grew with data size."),
            ("Export job holding the database busy", "A nightly export runs a huge join and slows all other traffic until it finishes."),
        ],
    },
]

_SEVERITIES = [Severity.SEV2, Severity.SEV3, Severity.SEV1, Severity.SEV4]


def scenario_keys() -> list[str]:
    return [s["key"] for s in SCENARIOS]


def scenario_of(tags: list[str]) -> str:
    """The scenario key stored in an incident's tags, or 'other' for non-seed data."""
    for tag in tags:
        if tag.startswith(SCENARIO_TAG_PREFIX):
            return tag[len(SCENARIO_TAG_PREFIX):]
    return "other"


def build_seed_incidents() -> list[Incident]:
    incidents: list[Incident] = []
    for s_index, scenario in enumerate(SCENARIOS):
        services = scenario["services"]
        for i, (title, description) in enumerate(scenario["variants"]):
            reported_at = BASE_DATE + datetime.timedelta(
                days=(s_index * 9 + i * 3) % 80, hours=(i * 5 + s_index) % 24
            )
            # Cycle statuses so resolved ones carry a root cause and resolution,
            # and the others do not: both shapes get searched.
            status = [IncidentStatus.RESOLVED, IncidentStatus.MITIGATED, IncidentStatus.OPEN][i % 3]
            resolved = status == IncidentStatus.RESOLVED
            incidents.append(
                Incident(
                    id=uuid.uuid5(SEED_NAMESPACE, f"{scenario['key']}:{i}"),
                    title=title,
                    description=description,
                    severity=_SEVERITIES[(s_index + i) % len(_SEVERITIES)],
                    status=status,
                    service=services[i % len(services)],
                    reported_at=reported_at,
                    resolved_at=reported_at + datetime.timedelta(hours=2 + i) if resolved else None,
                    root_cause=scenario["root_cause"] if resolved else None,
                    resolution=scenario["resolution"] if resolved else None,
                    tags=[SEED_TAG, f"{SCENARIO_TAG_PREFIX}{scenario['key']}"],
                )
            )
    return incidents
