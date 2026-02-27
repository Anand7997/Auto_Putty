# Local Test Execution Agent Setup Guide

## Overview

Your test automation application now supports **local test execution**! This means clients can run tests on their local machines instead of the server, allowing them to see the browser in action and have better control over the testing process.

## How It Works

1. **Server-side**: Your Flask application now includes agent management capabilities
2. **Client-side**: Clients install a local agent that connects to your server
3. **Execution**: When tests are triggered, they run on the client's local Chrome browser
4. **Results**: Test results are sent back to the server and displayed in the web interface

## Setup Instructions

### 1. Server Setup (Your Side)

Your server is already configured with the agent system. Make sure you have:

```bash
# Install required dependencies
pip install flask-socketio

# Your server now runs with SocketIO support
python app.py
```

The server will start on `http://localhost:5000` with WebSocket support for agent communication.

### 2. Client Setup (Client Side)

#### Option A: Download via Web Interface

1. Clients visit: `http://your-server:5000/agent/download`
2. Click "Download Test Agent Package"
3. Extract the downloaded ZIP file
4. Run the installer:
   - **Windows**: Double-click `install_windows.bat` OR run `python install_agent.py --server http://your-server:5000`
   - **Linux/Mac**: Run `python3 install_agent.py --server http://your-server:5000`

#### Option B: Manual Distribution

1. Build the agent package:
   ```bash
   cd agent
   python build_agent_package.py --server http://your-server:5000
   ```

2. Send the generated ZIP file to clients

3. Clients extract and install as above

### 3. Starting the Agent

After installation, clients can start the agent:

- **Windows**: Use the desktop shortcut "Start Test Agent" or run `start_agent.bat`
- **Linux/Mac**: Run `start_agent.sh`
- **Manual**: `python local_test_agent.py --server http://your-server:5000`

### 4. Using the System

1. **Check Agent Status**: Visit `http://your-server:5000/agent/download` to see connected agents
2. **Execute Tests**: In your web application, you can now choose execution mode:
   - **Server Mode**: Tests run on server (existing behavior)
   - **Agent Mode**: Tests run on client's local machine

## API Endpoints

Your server now includes these new endpoints:

- `GET /agent/download` - Agent download page
- `GET /api/download/agent` - Download agent package
- `GET /api/agents/list` - List connected agents
- `POST /api/agents/register` - Agent registration
- `POST /api/agents/test_result` - Receive test results from agents
- `POST /api/execute/<testcase_name>` - Enhanced to support agent execution

## Frontend Integration

Use the new React components:

```tsx
import { AgentSelector } from './components/AgentSelector';
import { TestExecutionWithAgent } from './components/TestExecutionWithAgent';

// In your test execution component
<TestExecutionWithAgent 
  testCaseName="your-test-case"
  onExecutionComplete={(result) => console.log(result)}
/>
```

## Client Requirements

Clients need:
- Python 3.7 or higher
- Google Chrome browser
- Internet connection to your server
- Windows, macOS, or Linux

## Troubleshooting

### Agent Won't Connect
- Check firewall settings
- Verify server URL is correct
- Ensure server is running with SocketIO support

### Tests Don't Execute Locally
- Verify Chrome is installed
- Check agent logs in `~/.test_agent/logs/`
- Ensure agent shows as "Online" in the web interface

### WebSocket Issues
- Make sure your server supports WebSocket connections
- Check if proxy/firewall blocks WebSocket traffic
- Verify Flask-SocketIO is installed: `pip install flask-socketio`

## Security Considerations

- Agents connect via WebSocket to your server
- Only registered agents can execute tests
- Test results are sent back to server for storage
- Consider using HTTPS/WSS for production

## File Structure

```
your-project/
├── agent/
│   ├── local_test_agent.py      # Main agent application
│   ├── install_agent.py         # Agent installer
│   ├── build_agent_package.py   # Package builder
│   └── requirements.txt         # Agent dependencies
├── new_backend/
│   ├── app.py                   # Enhanced with agent support
│   ├── agent_manager.py         # Agent management
│   └── templates/
│       └── agent_download.html  # Download page
└── src/components/
    ├── AgentSelector.tsx        # Agent selection UI
    └── TestExecutionWithAgent.tsx # Execution with agent support
```

## Example Usage

1. **Client installs agent**: Downloads and runs installer
2. **Agent connects**: Shows up in server's agent list
3. **User executes test**: Chooses "Local Machine" mode
4. **Test runs locally**: Chrome opens on client's machine
5. **Results sync**: Test results appear in web interface

## Benefits

- **Visibility**: Clients can see tests running in real-time
- **Debugging**: Easier to debug issues when you can see the browser
- **Performance**: Reduces server load
- **Flexibility**: Clients can run tests on their specific environment
- **Control**: Clients can interact with tests if needed

## Next Steps

1. Test the system with a client machine
2. Update your documentation for users
3. Consider adding authentication for production use
4. Monitor agent connections and performance

Your test automation system now supports both server and local execution modes!