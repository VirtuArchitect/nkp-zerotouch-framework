# Proxied AHV Provider

Status: implemented baseline through the Nutanix AHV command path.

This provider profile models AHV deployments where external access is routed
through an enterprise proxy.

Additional inputs:

- HTTP/HTTPS proxy URL.
- No-proxy rules for Prism Central, registry, service networks, and cluster
  endpoints.
- Optional registry mirror endpoint.

Generated deploy assets include proxy-related NKP flags when configured.
