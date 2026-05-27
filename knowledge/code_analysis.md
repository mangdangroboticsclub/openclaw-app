# Code Analysis Capabilities

Last updated: 2026-05-15

## Overview

Code analysis tools automatically examine source code, dependencies, and configurations to uncover security vulnerabilities, code quality issues, and compliance gaps. The field has evolved significantly with AI integration becoming the new dividing line in 2025-2026.

## Types of Code Analysis

1. **Static Application Security Testing (SAST)** - White-box method analyzing source code before execution (shift left).
2. **Dynamic Application Security Testing (DAST)** - Black-box testing running applications by simulating attacks.
3. **Software Composition Analysis (SCA)** - Evaluates third-party components for vulnerabilities and licensing issues.
4. **Secrets Scanning** - Detects hardcoded credentials, keys, and tokens across full codebase history.
5. **Infrastructure as Code (IaC) Scanning** - Evaluates IaC and cloud config files for misconfigurations pre-deployment.
6. **AI-Powered Code Review** - Uses context-aware AI to catch logic errors, architectural anti-patterns, and context-dependent issues.

## Top SAST Tools (2026)

- **DeepSource** - Hybrid engine: 5000+ deterministic rules + AI review agent. Highest OpenSSF F1 score (84.51%).
- **SonarQube** - Industry-standard code quality; broad language support; on-prem option.
- **Semgrep** - Fast, pattern-based SAST; great for custom rules.
- **Checkmarx** - Enterprise SAST with deep language support.
- **Snyk Code** - Developer-first; strong SCA + SAST combo.
- **Veracode** - Mature platform; broad compliance coverage.
- **Codacy** - Code quality + security; good CI/CD integration.
- **CodeAnt AI** - AI-native; auto-fix suggestions.
- **Qodana** - JetBrains IDE integration.

## Key Evaluation Criteria

- **Rule depth and accuracy** - Number of rules matters less than precision. High false positive rates kill adoption.
- **AI integration** - Modern tools combine deterministic rules with AI that understands codebase context and data-flow.
- **Language support** - Must go deep, not just wide.
- **Developer workflow** - Findings inline on PRs get acted on; separate dashboards get ignored.
- **Platform scope** - SAST + SCA + secrets + IaC in one platform replaces 3-5 point solutions.

## Open Source Options

- Semgrep - Free and open-source SAST engine
- SonarQube Community Edition - Open-source code quality
- OWASP Dependency-Check - SCA for known CVEs
- Bandit - Python security linter
- TruffleHog - Secrets scanning
- ESLint with security plugins - JS/TS linting + security rules
