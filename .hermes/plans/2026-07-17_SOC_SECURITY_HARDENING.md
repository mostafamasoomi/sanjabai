# SOC Security Hardening Plan — Multiai

> **Goal:** Bring all 5 security dimensions to 9+/10 through systematic senior-managed improvements.

**Architecture:** Wazuh SIEM + Multiai App Security + Financial Watchdog + SOC Dashboard — all integrated.

**Current Scores:**
| Dimension | Current | Target |
|---|---|---|
| Application Security | 7/10 | 9+ |
| Infrastructure Security | 4/10 | 9+ |
| SOC/SIEM | 3/10 | 9+ |
| Incident Response | 2/10 | 9+ |
| **Overall** | **4/10** | **9+** |

---

## Phase 1: Infrastructure Security (4→9) 🔴 CRITICAL

### Task 1.1: Change Wazuh Indexer Password
- **File:** `docker-compose.yml` (wazuh section)
- **Action:** Set strong admin password via `OPENSEARCH_INITIAL_ADMIN_PASSWORD`
- **Verify:** `curl -u admin:NEW_PASS https://localhost:9200`

### Task 1.2: Block External Access to Ports 2057/9200
- **Action:** Configure firewall rules
- **Verify:** `curl from external IP → timeout`

### Task 1.3: Add Resource Limits to Wazuh Containers
- **File:** `docker-compose.yml`
- **Add:** `mem_limit`, `cpus` for wazuh-manager, indexer, dashboard

### Task 1.4: Network Isolation
- **Action:** Wazuh containers only accessible from internal network
- **File:** `docker-compose.yml` — remove port bindings, use internal DNS

---

## Phase 2: SOC/SIEM Integration (3→9)

### Task 2.1: Install Wazuh Agent on Multiai API
- **Action:** Add wazuh-agent container to docker-compose
- **Config:** Point to wazuh-manager:1514
- **Verify:** Agent appears in Wazuh dashboard

### Task 2.2: Log Forwarding from Multiai to Wazuh
- **Action:** Configure rsyslog/filebeat in API container
- **Forward:** FastAPI access logs, auth logs, watchdog alerts
- **Verify:** Logs appear in Wazuh index

### Task 2.3: Custom Wazuh Rules for Multiai
- **File:** `/var/ossec/etc/rules/local_rules.xml`
- **Rules:** 
  - Failed login attempts (brute force detection)
  - Admin privilege escalation
  - Financial anomaly alerts
  - Rate limit violations
  - Unusual API access patterns

### Task 2.4: Wazuh Active Response for Multiai
- **Action:** Configure active response to auto-block IPs
- **Integration:** Wazuh → firewall-drop on critical alerts

---

## Phase 3: Application Security (7→9)

### Task 3.1: Account Lockout System
- **File:** `backend/security.py`
- **Action:** Redis-based lockout after 5 failed attempts
- **Duration:** 15 min lockout, escalating to 1 hour
- **Alert:** Telegram notification on lockout

### Task 3.2: Admin MFA (TOTP)
- **File:** `backend/admin.py`, `frontend/app/admin/AdminPanel.tsx`
- **Action:** Optional TOTP for admin login
- **Store:** Secret in DB, verify with pyotp library

### Task 3.3: Enhanced Audit Trail
- **File:** `backend/admin.py`
- **Action:** Log all admin actions with IP, user-agent, timestamp
- **Query:** New endpoint `/admin/audit-logs` with pagination

### Task 3.4: Session Security
- **File:** `backend/security.py`
- **Action:** Session rotation on privilege change, concurrent session limit

---

## Phase 4: SOC Dashboard in Admin Panel

### Task 4.1: Security Tab in AdminPanel
- **File:** `frontend/app/admin/AdminPanel.tsx`
- **New page:** `security` with:
  - Real-time alert feed (WebSocket from Wazuh)
  - Failed login attempts chart
  - Active sessions monitor
  - Banned users list
  - Threat level indicator

### Task 4.2: Backend SOC Endpoints
- **File:** `backend/soc.py` (new)
- **Endpoints:**
  - `GET /admin/soc/alerts` — recent alerts from Wazuh
  - `GET /admin/soc/threats` — aggregated threat data
  - `GET /admin/soc/sessions` — active sessions
  - `GET /admin/soc/audit` — audit log with filters

### Task 4.3: Real-time Alert WebSocket
- **File:** `backend/soc.py`, `frontend/app/admin/AdminPanel.tsx`
- **Action:** WebSocket connection for live alerts

---

## Phase 5: Watchdog → Wazuh Integration

### Task 5.1: Watchdog Alert Forwarding
- **File:** `backend/watchdog.py`
- **Action:** After Telegram alert, also POST to Wazuh indexer
- **Index:** `soc-panel-alerts`

### Task 5.2: Unified Alert Schema
- **Action:** Standardize alert format across watchdog and Wazuh
- **Fields:** severity, source, message, timestamp, metadata

---

## Execution Strategy

Each phase managed by a senior subagent:
1. **Phase 1** — DevOps Senior (infrastructure hardening)
2. **Phase 2** — SOC/SIEM Senior (Wazuh integration)
3. **Phase 3** — Security Architect (app security)
4. **Phase 4** — Full-Stack Senior (SOC dashboard)
5. **Phase 5** — Backend Senior (watchdog integration)

After each phase: **evaluation** → if score < 9, iterate.

## Verification Checklist
- [ ] Wazuh indexer password changed
- [ ] Ports 2057/9200 not externally accessible
- [ ] Wazuh agent connected and reporting
- [ ] Multiai logs forwarding to Wazuh
- [ ] Custom rules triggering correctly
- [ ] Account lockout working
- [ ] Audit trail complete
- [ ] SOC dashboard functional
- [ ] Watchdog alerts in Wazuh
- [ ] All tests passing
- [ ] Git commit + push
