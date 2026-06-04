# Config Reference

The environment YAML is the source of truth for ZeroTouch.

## environment

- `name`: local environment name used under `.zt/environments/`
- `type`: one of `connected`, `proxied`, or `air-gapped`
- `proxy`: required for `proxied`

## nkp

- `version`: NKP version, for example `v2.17.1`
- `bundleType`: `standard` or `air-gapped`
- `bundlePath`: extracted bundle path, preferably Linux/WSL style

## nutanix

- `prismCentralEndpoint`: Prism Central URL
- `clusterName`: Prism Element cluster name
- `subnetName`: Prism subnet name
- `imageName`: VM image name for NKP nodes
- `storageContainer`: CSI storage container
- `project`: Prism Central project for node resources

## cluster

- `name`: NKP cluster name
- `kubernetesVersion`: Kubernetes version
- `controlPlaneEndpointIp`: static API endpoint IP
- `controlPlaneEndpointPort`: API endpoint port
- `controlPlaneReplicas`: control plane count
- `workerReplicas`: worker count
- `podCidr`: pod CIDR
- `serviceCidr`: service CIDR
- `loadBalancerIpRange`: service load balancer IP range
- `ntpServers`: list of NTP servers
- `sshPublicKeyFile`: SSH public key path on the runner
- `sshUsername`: node SSH username
- `selfManaged`: whether the cluster is self-managed
- `fips`: enable FIPS workflow

## registry

- `endpoint`: registry host and port
- `namespace`: registry namespace
- `insecure`: registry push TLS behavior
- `caCert`: registry CA certificate path
