# 🚀 IXIGO Test Automation System - Startup Guide

## Quick Start Commands

### Option 1: One-Click Startup (Recommended)

**Windows:**
```bash
start.bat
```

**Linux/Mac:**
```bash
./start.sh
```

### Option 2: NPM Commands

**Setup (First time only):**
```bash
npm run setup
```

**Start everything:**
```bash
npm start
```

**Individual services:**
```bash
npm run dev          # Frontend only
npm run backend      # Backend only
```

## What Gets Started

1. **Backend Flask API** (Port 5000)
   - REST API endpoints
   - Database connection to SQL Server
   - Selenium test executor

2. **Frontend React App** (Port 5173)
   - Modern UI with light theme
   - Module management interface
   - Real-time test execution

3. **Database Connection**
   - SQL Server: `LPT2084-B1`
   - Database: `Ixigo_TestAutomation`

## Prerequisites

- **Node.js** (v16 or higher)
- **Python** (v3.8 or higher)
- **SQL Server** with Ixigo_TestAutomation database
- **Chrome Browser** (for Selenium tests)

## Troubleshooting

### Port Already in Use
If ports 5000 or 5173 are busy:
- Kill existing processes
- Or modify port in `vite.config.ts` (frontend) or `new_backend/app.py` (backend)

### Python Dependencies
If backend fails to start:
```bash
cd new_backend
pip install -r requirements.txt
```

### Frontend Dependencies
If frontend fails to start:
```bash
npm install
```

## System URLs

- **Frontend:** http://localhost:5173
- **Backend API:** http://localhost:5000
- **Health Check:** http://localhost:5000/api/health

## Available NPM Scripts

- `npm run setup` - Install all dependencies (frontend + backend)
- `npm start` - Start both frontend and backend
- `npm run dev` - Start frontend only
- `npm run backend` - Start backend only
- `npm run build` - Build frontend for production
- `npm run install-backend` - Install Python dependencies
