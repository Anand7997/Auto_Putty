# 🚀 Complete Installation & Usage Guide
## Ixigo Selenium Test Automation Framework

### 📋 Prerequisites Check

**Before starting, ensure you have:**
- ✅ Windows 10/11
- ✅ Python 3.8+ installed
- ✅ Node.js 16+ installed
- ✅ SQL Server with "Ixigo_TestAutomation" database
- ✅ Chrome browser installed

---

## 🔧 Step 1: Install Allure CLI

### Option A: Using NPM (Recommended)
```bash
# Open Command Prompt as Administrator
npm install -g allure-commandline

# Verify installation
allure --version
```

### Option B: Manual Download
1. Download from: https://github.com/allure-framework/allure2/releases
2. Extract to `C:\allure`
3. Add `C:\allure\bin` to system PATH
4. Restart Command Prompt and verify: `allure --version`

---

## 📦 Step 2: Install Python Dependencies

```bash
# Navigate to your project folder
cd C:\Users\VAnand\Downloads\ixigo-test-pilot-tool-main

# Install backend dependencies
cd backend
pip install -r requirements.txt
pip install allure-pytest allure-python-commons

# Go back to root
cd ..
```

---

## 🌐 Step 3: Install Frontend Dependencies

```bash
# Install frontend dependencies
npm install

# Verify installation
npm list
```

---

## 🗄️ Step 4: Database Setup Verification

### Check Database Connection:
```bash
# Test database connection
cd backend
python -c "
from app import get_db_connection
try:
    conn = get_db_connection()
    print('✅ Database connection successful!')
    conn.close()
except Exception as e:
    print(f'❌ Database error: {e}')
"
```

---

## 🎯 Step 5: Start the Application

### Terminal 1: Start Backend Server
```bash
# Navigate to backend folder
cd backend

# Start Flask server
python app.py
```
**Expected Output:**
```
🏁 Starting Flask API Server
📊 Database: Ixigo_TestAutomation on LPT2084-B1
🌐 Server: http://localhost:5000
* Running on http://127.0.0.1:5000
```

### Terminal 2: Start Frontend Server
```bash
# Open new terminal in project root
npm run dev
```
**Expected Output:**
```
VITE v5.4.10  ready in 537 ms
➜  Local:   http://localhost:8080/
➜  Network: http://192.168.1.7:8080/
```

---

## 🎮 Step 6: Using the Application

### 1. Access the Web Interface
- Open browser: `http://localhost:8080`
- You should see the **Selenium Test Automation Framework** with red "V" favicon

### 2. Create a Project
1. Click **"Create Project"** button
2. Enter project name: e.g., "Flight_Booking_Tests"
3. Add description
4. Click **"Create Project"**

### 3. Create Test Case
1. Select your project
2. Click **"Create Test Case"**
3. Enter test case name: e.g., "Search_Flight_Delhi_Mumbai"
4. Add description
5. Click **"Create Test Case"**

### 4. Configure Test Steps
1. Select your test case
2. Click **"Configure Test Steps"**
3. Add test steps with required fields:
   - **TC ID**: TC001
   - **Step No**: 1, 2, 3...
   - **Description**: "Open browser", "Select from city", etc.
   - **Element Name**: Browser, From, To, etc.
   - **Action Type**: OPEN_BROWSER, CLICK_AND_SELECT, etc.
   - **XPath**: Your element XPaths
   - **Values**: URLs, city names, etc.

### 5. Execute Tests
1. Review test steps in **"Test Summary"**
2. Click **"Run Test Cases"**
3. Watch Chrome launch and execute your tests
4. View results in **"Results Dashboard"**

---

## 📊 Step 7: Generate Allure Reports

### Method 1: Automated Script (Recommended)
```bash
# In project root
python generate_allure_report.py

# Select option 1: "Generate and serve report"
# Report will open automatically in browser
```

### Method 2: Manual Commands
```bash
# After running tests
allure serve allure-results

# Or generate static report
allure generate allure-results --output allure-report --clean
```

---

## 🎯 Step 8: Sample Test Case Creation

### Example: Flight Search Test
```
Step 1:
- TC ID: TC001
- Step No: 1
- Description: Open Ixigo website
- Element Name: Browser
- Action Type: OPEN_BROWSER
- XPath: (leave empty)
- Values: https://www.ixigo.com/flights

Step 2:
- TC ID: TC001
- Step No: 2
- Description: Select departure city
- Element Name: From
- Action Type: CLICK_AND_SELECT
- XPath: //*[contains(text(),'From')]
- Values: Delhi

Step 3:
- TC ID: TC001
- Step No: 3
- Description: Select destination city
- Element Name: To
- Action Type: CLICK_AND_SELECT
- XPath: //*[contains(text(),'To')]
- Values: Mumbai
```

---

## 🔍 Step 9: Verification Checklist

### ✅ Backend Health Check:
- [ ] Backend server running on port 5000
- [ ] Database connection successful
- [ ] API endpoints responding

### ✅ Frontend Health Check:
- [ ] Frontend running on port 8080
- [ ] Custom "V" favicon visible
- [ ] All navigation working
- [ ] Forms submitting successfully

### ✅ Test Execution Check:
- [ ] Chrome launches without automation indicators
- [ ] Test steps execute in sequence
- [ ] Screenshots captured
- [ ] Results saved to database

### ✅ Allure Reports Check:
- [ ] Allure CLI installed and working
- [ ] Reports generate successfully
- [ ] Interactive dashboard accessible
- [ ] Screenshots and logs visible

---

## 🐛 Troubleshooting Common Issues

### Issue 1: "Failed to create project"
**Solution:**
```bash
# Check database connection
cd backend
python -c "from app import get_db_connection; get_db_connection()"
```

### Issue 2: "Chrome not launching"
**Solution:**
```bash
# Test Chrome driver
cd backend
python -c "
from test_executor import TestExecutor
executor = TestExecutor()
executor.launch_browser()
executor.close_browser()
print('✅ Chrome test successful!')
"
```

### Issue 3: "Allure command not found"
**Solution:**
```bash
# Reinstall Allure CLI
npm uninstall -g allure-commandline
npm install -g allure-commandline
allure --version
```

### Issue 4: "Frontend not loading"
**Solution:**
```bash
# Clear cache and restart
npm run build
npm run dev
```

---

## 🎉 Success Indicators

### You're ready when you see:
1. ✅ **Backend**: Flask server running on port 5000
2. ✅ **Frontend**: Vite server running on port 8080  
3. ✅ **Database**: Projects and test cases saving successfully
4. ✅ **Chrome**: Launching without automation indicators
5. ✅ **Allure**: Reports generating with charts and screenshots

---

## 📞 Quick Commands Reference

```bash
# Start Backend
cd backend && python app.py

# Start Frontend  
npm run dev

# Generate Allure Reports
python generate_allure_report.py

# Test Database Connection
cd backend && python -c "from app import get_db_connection; print('✅ DB OK' if get_db_connection() else '❌ DB Error')"

# Test Chrome Launch
cd backend && python -c "from test_executor import TestExecutor; TestExecutor().launch_browser()"
```

---

## 🎯 Next Steps

1. **Create your first test case** using the web interface
2. **Execute the test** and watch Chrome automation
3. **Generate Allure report** to see beautiful analytics
4. **Scale up** by adding more complex test scenarios

**Happy Testing! 🚀**
