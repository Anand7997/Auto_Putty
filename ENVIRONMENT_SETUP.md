# Environment Setup Guide

This project supports two different environment configurations for different use cases.

## 🏠 Local Development Environment (`.env.local`)

**Use this for:** Developers working locally on their machines

**Configuration:**
- Frontend: `http://localhost:8083/`
- Backend: `http://localhost:5001/`

**How to use:**
```bash
# Method 1: Use npm script (recommended)
npm run start:local

# Method 2: Manual setup
npm run env:local
npm run start

# Method 3: Copy manually
copy .env.local .env
npm run start
```

## 👥 Team Collaboration Environment (`.env.team`)

**Use this for:** Team members accessing the application through VS Code dev tunnels

**Configuration:**
- Frontend: `https://29tv5wlb-8083.inc1.devtunnels.ms/`
- Backend: `https://29tv5wlb-5001.inc1.devtunnels.ms/`

**How to use:**
```bash
# Method 1: Use npm script (recommended)
npm run start:team

# Method 2: Manual setup
npm run env:team
npm run start

# Method 3: Copy manually
copy .env.team .env
npm run start
```

## 🔧 Available Scripts

| Script | Description |
|--------|-------------|
| `npm run start:local` | Start with local development environment |
| `npm run start:team` | Start with team collaboration environment |
| `npm run env:local` | Switch to local environment configuration |
| `npm run env:team` | Switch to team environment configuration |
| `npm run start` | Start both frontend and backend with current .env |

## 📁 Environment Files

| File | Purpose |
|------|---------|
| `.env` | Active environment configuration (auto-generated) |
| `.env.local` | Local development template |
| `.env.team` | Team collaboration template |

## 🚀 Quick Start

### For Developers (Local Development)
```bash
npm run start:local
```

### For Team Members (Remote Access)
```bash
npm run start:team
```

## 🔍 Environment Variables

| Variable | Local Value | Team Value | Description |
|----------|-------------|------------|-------------|
| `VITE_API_BASE_URL` | `http://localhost:5001` | `https://29tv5wlb-5001.inc1.devtunnels.ms` | Backend API URL |
| `NODE_ENV` | `development` | `development` | Node environment |
| `VITE_ENV` | `local` | `team` | Environment identifier |
| `VITE_DEV_MODE` | `true` | `false` | Development mode flag |
| `VITE_DEBUG` | `true` | `false` | Debug mode flag |

## 📝 Notes

1. **Never commit `.env`** - It's auto-generated and should be in `.gitignore`
2. **Dev Tunnel URLs** - Update the URLs in `.env.team` if your dev tunnel URLs change
3. **CORS Configuration** - The backend is already configured to accept requests from both localhost and dev tunnel URLs
4. **Port Configuration** - Frontend runs on port 8083, backend on port 5001

## 🛠️ Troubleshooting

### Issue: Environment not switching
**Solution:** Make sure to run the environment switch command before starting:
```bash
npm run env:local  # or npm run env:team
npm run start
```

### Issue: CORS errors
**Solution:** Check that the backend CORS configuration includes your frontend URL. The backend already includes common dev tunnel patterns.

### Issue: Dev tunnel URLs changed
**Solution:** Update the URLs in `.env.team` file with your new dev tunnel URLs.