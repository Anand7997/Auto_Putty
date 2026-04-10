# Automation Pro Suite

An end-to-end QA automation platform that brings requirement analysis, automation planning, low-code testcase design, multi-engine execution, live monitoring, and rich reporting into one integrated workspace.

## Overview

Automation Pro Suite is built for teams that want more than a folder of test scripts. It provides a full-stack control center for managing the entire automation lifecycle, from uploading BRDs and generating testcases to executing suites with Selenium, Playwright, or Cypress and reviewing results through Allure and Extent reports.

The project combines a React + Vite frontend with a Flask backend, SQL Server persistence, browser automation executors, Excel-driven test data mapping, real-time monitoring, role-based authorization, and a Chrome extension for XPath capture. The result is a practical platform for teams that need visibility, repeatability, and scale in their QA workflow.

## Why This Repo Stands Out

- Unifies the full testing lifecycle instead of focusing only on script execution
- Supports Selenium, Playwright, and Cypress from a single platform
- Connects requirements and BRDs directly to testcase generation
- Includes live noVNC-based execution monitoring for remote visibility
- Supports data-driven execution through Excel mapping
- Generates polished reports with Allure and Extent integrations
- Adds user approval and function-level authorization for team usage
- Includes page object and XPath management to reduce maintenance effort

## Core Capabilities

### 1. Requirements and Feasibility Analysis
- Upload BRD documents, PDFs, and Excel files
- Organize requirement inputs inside the platform
- Generate testcases from BRD content using AI-assisted flows
- Support requirement-driven automation planning

### 2. Automation Planning and Design
- Create projects, modules, test suites, and testcases
- Define structured test steps and execution flow
- Manage reusable page objects and application elements
- Map automation assets to business modules clearly

### 3. Automation Development
- Build testcase steps through a UI-driven workflow
- Manage page objects and XPath repositories
- Refresh object mappings when locators change
- Capture XPath data with the bundled Chrome extension

### 4. Multi-Engine Execution
- Execute tests with Selenium WebDriver
- Run modern browser automation with Playwright
- Support Cypress-based execution flows
- Trigger local and server-side runs from the same platform

### 5. Live Monitoring and Remote Viewing
- Track executions in real time
- Stream browser sessions through noVNC
- Support remote viewing for server-side runs
- Monitor session health and execution progress

### 6. Data-Driven Testing
- Upload Excel files for execution data
- Map Excel sheets to testcases
- Reuse structured datasets across executions
- Combine business data and automation logic in one flow

### 7. Reporting and Analysis
- Generate Allure reports
- Generate Extent reports
- Publish dashboard-style execution results
- Review execution history and detailed test outcomes

### 8. Team and Access Management
- User signup and approval workflow
- Function-level authorization
- Controlled access to planning, development, execution, and reporting modules

## Architecture

### Frontend
- React 18
- Vite
- TypeScript
- Tailwind CSS
- Radix UI / shadcn-style UI components

### Backend
- Flask
- Flask-SocketIO
- Flask-CORS
- Python-based execution and orchestration services

### Execution Engines
- Selenium
- Playwright
- Cypress

### Data and Integrations
- SQL Server via `pyodbc`
- Excel parsing with `pandas` and `openpyxl`
- PDF and DOCX parsing for BRD workflows
- Chrome extension for XPath capture

### Reporting and Monitoring
- Allure
- Extent Reports
- noVNC / remote session streaming

## Product Flow

1. Upload BRD, PDF, or Excel requirement files
2. Create projects, modules, and test structures
3. Generate or design testcases and steps
4. Map page objects, locators, and data sources
5. Execute with Selenium, Playwright, or Cypress
6. Monitor the run locally or through remote viewing
7. Analyze results in Allure, Extent, and dashboard views

## Tech Stack

### Frontend
- React
- TypeScript
- Vite
- Tailwind CSS
- React Router
- TanStack Query
- Recharts

### Backend
- Python
- Flask
- Flask-SocketIO
- Selenium
- Playwright
- OpenCV
- pandas
- PyPDF2
- python-docx

### Tooling
- Cypress
- Allure
- Extent Reports
- Chrome Extension APIs

## Repository Structure

```text
.
|-- src/                     # React frontend application
|-- new_backend/             # Flask backend and execution engine
|-- chrome-extension/        # XPath capture and browser-side helper tooling
|-- cypress_test/            # Cypress test assets
|-- cypress_runtime_project/ # Runtime Cypress execution project
|-- tools/                   # Reporting and supporting utilities
|-- allure-report/           # Generated Allure output
|-- extent-report/           # Generated Extent output
|-- published-results/       # Published dashboard results
```

## Getting Started

### Prerequisites

- Node.js
- Python 3
- SQL Server access
- npm

### Install

```bash
npm install
npm run install-backend
```

Or use the combined setup script:

```bash
npm run setup
```

### Run the Full Stack App

```bash
npm start
```

Available scripts from `package.json`:

- `npm run dev` starts the frontend
- `npm run backend` starts the Flask backend
- `npm start` starts frontend and backend together
- `npm run setup` installs frontend and backend dependencies
- `npm run env:local` switches to local environment settings
- `npm run env:team` switches to team environment settings
- `npm run env:server` switches to server environment settings

### Optional Startup Helpers

Windows:

```bat
start.bat
```

Linux/macOS-style shell:

```bash
./start.sh
```

## Key Backend Highlights

- REST APIs for users, authorization, planning, testcase management, execution, reporting, BRD processing, Excel mapping, and monitoring
- Socket-based events for live execution session updates
- Dedicated executors for Selenium, Playwright, and Cypress
- Server-side execution orchestration with remote viewing support
- Report generation endpoints for Allure and Extent

## Key Frontend Highlights

- Authentication and approval-aware dashboard flow
- Lifecycle-based navigation across requirements, planning, development, execution, reporting, and maintenance
- UI modules for testcase creation, step management, suite management, reporting, and live monitoring
- Authorization-aware feature access for team workflows

## Best Use Cases

- Internal QA platforms
- Enterprise automation dashboards
- Teams migrating from manual testing to structured automation
- Data-driven automation projects
- Multi-framework execution environments
- Requirement-to-testcase acceleration workflows

## README Pitch

Automation Pro Suite transforms test automation from a collection of scripts into a complete operational platform. It connects requirement intake, testcase design, locator management, execution orchestration, remote visibility, and reporting so QA teams can build, run, and scale automation with much more clarity and control.

## Current Notes

- The repository appears designed for an environment with SQL Server connectivity and team-specific network configuration
- Generated reports, runtime artifacts, and supporting documentation are already included in the repo
- Environment switching is supported through the included scripts and `.env` variants

## Future-Friendly Positioning

This project is a strong foundation for building a modern QA command center: one place where product requirements, automation assets, live execution, and result intelligence come together.
