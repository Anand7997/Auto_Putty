# QFast Authentication Module

This document provides complete setup and usage instructions for the authentication module built for the QFast application.

## Overview

The authentication module provides secure user registration and login functionality with the following features:

- User registration with username, email, and password
- Secure password hashing (not stored in plain text)
- User login with email/password
- Automatic redirection to signup if login credentials are not found
- Protected routes and session management
- Clean, responsive UI using Bootstrap/Material UI design principles
- SQL Server database integration

## Architecture

- **Frontend**: React with TypeScript, Tailwind CSS, shadcn/ui components
- **Backend**: Flask with SQLAlchemy-style database operations
- **Database**: SQL Server (SSMS) with pyodbc connection
- **Security**: Werkzeug password hashing

## Database Setup

### 1. Create the Authentication Table

Run the following SQL script in SQL Server Management Studio (SSMS) on your `Ixigo_TestAutomation` database:

```sql
-- SQL Server Database Setup for Authentication Module
-- Run this script in SQL Server Management Studio (SSMS) on your Ixigo_TestAutomation database

USE Ixigo_TestAutomation;
GO

-- Create Authentication table
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Authentication' AND xtype='U')
CREATE TABLE Authentication (
    id INT IDENTITY(1,1) PRIMARY KEY,
    username NVARCHAR(255) NOT NULL UNIQUE,
    email NVARCHAR(255) NOT NULL UNIQUE,
    password_hash NVARCHAR(255) NOT NULL,
    created_at DATETIME DEFAULT GETDATE(),
    last_login DATETIME NULL,
    is_active BIT DEFAULT 1
);
GO

-- Create index on email for faster lookups
CREATE INDEX IX_Authentication_Email ON Authentication(email);
GO

-- Create index on username for faster lookups
CREATE INDEX IX_Authentication_Username ON Authentication(username);
GO

-- Optional: Create a login attempts table for security (future enhancement)
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='LoginAttempts' AND xtype='U')
CREATE TABLE LoginAttempts (
    id INT IDENTITY(1,1) PRIMARY KEY,
    email NVARCHAR(255) NOT NULL,
    attempt_time DATETIME DEFAULT GETDATE(),
    success BIT DEFAULT 0,
    ip_address NVARCHAR(45) NULL
);
GO

PRINT 'Authentication module database setup completed successfully!';
GO
```

### 2. Database Configuration

The database connection is already configured in `new_backend/app.py`:

```python
DB_CONFIG = {
    'server': 'LPT2084-B1',
    'database': 'Ixigo_TestAutomation',
    'driver': 'ODBC Driver 17 for SQL Server',
    'uid': 'myuser',
    'pwd': 'MyPass135'
}
```

Update these values according to your SQL Server setup.

## Backend Setup

### 1. Install Dependencies

The required dependencies have been added to `new_backend/requirements.txt`:

```
Flask==2.3.3
Flask-CORS==4.0.0
pyodbc==5.2.0
selenium==4.15.0
webdriver-manager==4.0.1
requests==2.31.0
playwright==1.55.0
Werkzeug==2.3.7
```

Install them by running:

```bash
cd new_backend
pip install -r requirements.txt
```

### 2. API Endpoints

The authentication module adds the following endpoints:

- `POST /api/signup` - User registration
- `POST /api/login` - User authentication

Both endpoints support CORS for React frontend communication.

## Frontend Setup

### 1. Components Created

- `src/components/Login.tsx` - Combined login/signup interface
- `src/components/Signup.tsx` - Dedicated signup form
- `src/components/Dashboard.tsx` - User dashboard after login

### 2. Routing Integration

The authentication flow is integrated into the main app routing in `src/App.tsx`:

- `/login` - Login page
- `/signup` - Signup page
- `/dashboard` - User dashboard (protected)
- `/app` - Main application (protected)

## Usage Flow

### 1. First Time User

1. User visits the application
2. Redirected to `/login`
3. User attempts to sign in
4. If credentials not found, automatically redirected to signup
5. User creates account
6. Redirected back to login
7. User signs in successfully
8. Redirected to dashboard
9. User can enter the main application

### 2. Returning User

1. User visits the application
2. If previously logged in, redirected to dashboard
3. Otherwise, goes through login flow
4. After successful login, redirected to dashboard

## Security Features

- Passwords are hashed using Werkzeug's `generate_password_hash`
- Password verification uses `check_password_hash`
- Input validation for username, email, and password
- SQL injection prevention through parameterized queries
- CORS properly configured for frontend-backend communication

## Running the Application

### 1. Start the Backend

```bash
cd new_backend
python app.py
```

The backend will run on `http://localhost:5000`

### 2. Start the Frontend

```bash
npm run dev
```

The frontend will run on `http://localhost:5173` (or your configured port)

### 3. Start Both Together

```bash
npm run start
```

This runs both backend and frontend concurrently.

## Testing the Authentication

### 1. Manual Testing

1. Open the application in your browser
2. Try signing up with a new account
3. Try logging in with the created credentials
4. Test the automatic redirection when trying to login with non-existent credentials
5. Test logout functionality

### 2. API Testing

You can test the endpoints directly:

**Signup:**
```bash
curl -X POST http://localhost:5000/api/signup \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"test@example.com","password":"password123"}'
```

**Login:**
```bash
curl -X POST http://localhost:5000/api/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password123"}'
```

## Troubleshooting

### Common Issues

1. **Database Connection Error**
   - Verify SQL Server is running
   - Check connection string in `new_backend/app.py`
   - Ensure ODBC Driver 17 for SQL Server is installed

2. **CORS Errors**
   - Ensure Flask-CORS is properly configured
   - Check that frontend is running on the expected port

3. **Password Hashing Issues**
   - Ensure Werkzeug is installed
   - Check that password hashing functions are imported correctly

4. **React Routing Issues**
   - Ensure all components are properly imported
   - Check that protected routes are correctly implemented

### Database Verification

Check if the Authentication table was created:

```sql
USE Ixigo_TestAutomation;
SELECT * FROM sysobjects WHERE name='Authentication' AND xtype='U';
```

Check table contents:

```sql
SELECT id, username, email, created_at, last_login, is_active FROM Authentication;
```

## Future Enhancements

- Password reset functionality
- Email verification
- Two-factor authentication
- Account lockout after failed attempts
- Session management with JWT tokens
- User roles and permissions

## Files Modified/Created

### Backend
- `new_backend/app.py` - Added authentication routes and password hashing
- `new_backend/requirements.txt` - Added Werkzeug dependency

### Frontend
- `src/App.tsx` - Added authentication routing and state management
- `src/components/Login.tsx` - Combined login/signup component
- `src/components/Signup.tsx` - Dedicated signup component
- `src/components/Dashboard.tsx` - User dashboard component

### Database
- `database_setup.sql` - SQL script for creating authentication tables

### Documentation
- `AUTHENTICATION_README.md` - This documentation file

## Support

For issues with the authentication module, check:
1. Flask backend logs in the terminal
2. Browser developer console for frontend errors
3. SQL Server logs for database issues
4. Network tab for API call failures