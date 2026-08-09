# doctorlib-navigator

[![Test](https://github.com/jo-hoe/doctorlib-navigator/actions/workflows/test.yml/badge.svg)](https://github.com/jo-hoe/doctorlib-navigator/actions/workflows/test.yml)
[![Coverage](https://coveralls.io/repos/github/jo-hoe/doctorlib-navigator/badge.svg?branch=main)](https://coveralls.io/github/jo-hoe/doctorlib-navigator?branch=main)
[![Release Image](https://github.com/jo-hoe/doctorlib-navigator/actions/workflows/image-release.yml/badge.svg)](https://github.com/jo-hoe/doctorlib-navigator/actions/workflows/image-release.yml)
[![Release Chart](https://github.com/jo-hoe/doctorlib-navigator/actions/workflows/chart-release.yml/badge.svg)](https://github.com/jo-hoe/doctorlib-navigator/actions/workflows/chart-release.yml)
[![Image version](https://ghcr.io/jo-hoe/doctorlib-navigator/badge/latest)](https://github.com/jo-hoe/doctorlib-navigator/pkgs/container/doctorlib-navigator)
[![Helm chart version](https://img.shields.io/github/v/release/jo-hoe/doctorlib-navigator?filter=doctorlib-navigator-*&label=chart)](https://github.com/jo-hoe/doctorlib-navigator/releases)

Polls the Doctolib API for available appointments and sends an email notification when slots open up. No browser automation needed — works via plain HTTP against the Doctolib JSON endpoints.

## Installation

```bash
helm repo add doctorlib-navigator https://jo-hoe.github.io/doctorlib-navigator
helm repo update
helm install doctorlib-navigator doctorlib-navigator/doctorlib-navigator \
  --set notification.email.username=<smtp-user> \
  --set notification.email.password=<smtp-password> \
  --set config.notification.email.smtp_host=smtp.example.com \
  --set config.notification.email.from_address=noreply@example.com \
  --set "config.notification.email.to_addresses={you@example.com}"
```

See [`charts/doctorlib-navigator/values.yaml`](charts/doctorlib-navigator/values.yaml) for all options, including how to configure `config.doctors`.
