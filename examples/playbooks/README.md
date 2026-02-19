# Example Remediation Playbooks

Example Ansible playbooks for use with the LogicMonitor MCP server's AAP integration.
These follow the `lm-remediate-<category>-<action>` naming convention for automatic discovery by the `/lm-remediate` skill.

## Naming Convention

Job templates in Ansible Automation Platform should use this pattern:

```
lm-remediate-<category>-<action>
```

Examples:
- `lm-remediate-disk-cleanup`
- `lm-remediate-service-restart`
- `lm-remediate-log-rotate`
- `lm-remediate-memory-cache-clear`

The `/lm-remediate` skill searches for templates matching `lm-remediate-*` to find available remediation actions.

## Importing into AAP

1. Create a project in AAP pointing to your Git repository containing these playbooks
2. Create a job template for each playbook:
   - **Name**: Use the `lm-remediate-*` naming convention
   - **Inventory**: Select your target inventory
   - **Playbook**: Point to the `.yml` file
   - **Extra Variables**: Enable "Prompt on Launch" so the MCP server can pass variables
3. Ensure the credential assigned to the template has SSH access to the target hosts

## Standard Variables

All playbooks accept `target_host` as an extra variable to scope execution via the Ansible `limit` parameter. Additional type-specific variables are documented in each playbook's header.

## Playbooks

| File | Purpose | Key Variables |
|------|---------|---------------|
| `lm-remediate-disk-cleanup.yml` | Clear temp files, old logs, journal | `target_host`, `min_age_days` |
| `lm-remediate-service-restart.yml` | Restart a named systemd service | `target_host`, `service_name` |
| `lm-remediate-log-rotate.yml` | Force logrotate and compress logs | `target_host`, `log_path` |
| `lm-remediate-memory-cache-clear.yml` | Drop page cache and restart heavy processes | `target_host`, `restart_services` |
