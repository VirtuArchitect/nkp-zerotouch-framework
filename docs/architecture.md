# Architecture

```mermaid
flowchart LR
  Config["Environment YAML"] --> Parser["tools/zt_config.py"]
  Parser --> Validate["validate"]
  Validate --> Prepare["prepare"]
  Prepare --> Workspace[".zt/environments/<name>"]
  Workspace --> Generate["generate"]
  Generate --> Plans["deploy.sh / registry.sh / plans"]
  Plans --> Review["plan review"]
  Review --> Registry["registry --apply (guarded)"]
  Review --> Deploy["deploy --apply (guarded)"]
  Deploy --> Kubeconfig["kubeconfig capture"]
  Kubeconfig --> Verify["verify"]
  Workspace --> Dashboard["Local dashboard"]
  Workspace --> Backup["backup"]
  Workspace --> Runs["runs"]
```

The repository tracks framework code, provider contracts, example configs, docs, tests, and packaging assets. Generated state and real secrets stay local under ignored paths.
