# doctorlib-navigator

[![Test](https://github.com/jo-hoe/doctorlib-navigator/actions/workflows/test.yml/badge.svg)](https://github.com/jo-hoe/doctorlib-navigator/actions/workflows/test.yml)
[![Coverage](https://coveralls.io/repos/github/jo-hoe/doctorlib-navigator/badge.svg?branch=main)](https://coveralls.io/github/jo-hoe/doctorlib-navigator?branch=main)
[![Release Image](https://github.com/jo-hoe/doctorlib-navigator/actions/workflows/image-release.yml/badge.svg)](https://github.com/jo-hoe/doctorlib-navigator/actions/workflows/image-release.yml)
[![Release Chart](https://github.com/jo-hoe/doctorlib-navigator/actions/workflows/chart-release.yml/badge.svg)](https://github.com/jo-hoe/doctorlib-navigator/actions/workflows/chart-release.yml)
[![Image version](https://img.shields.io/github/v/tag/jo-hoe/doctorlib-navigator?label=image)](https://github.com/jo-hoe/doctorlib-navigator/pkgs/container/doctorlib-navigator)
[![Helm chart version](https://img.shields.io/badge/chart-0.6.0-blue)](https://github.com/jo-hoe/doctorlib-navigator/pkgs/container/charts%2Fdoctorlib-navigator)

Polls the Doctolib API for available appointments and sends an email notification when slots open up. No browser automation needed — works via plain HTTP against the Doctolib JSON endpoints.

## Installation

```bash
helm install doctorlib-navigator oci://ghcr.io/jo-hoe/charts/doctorlib-navigator \
  --version 0.5.0
```

See [`charts/doctorlib-navigator/values.yaml`](charts/doctorlib-navigator/values.yaml) for all options, including how to configure `config.doctors`.
