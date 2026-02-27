
import React, { useState, useEffect } from 'react';
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Index from "./pages/Index";
import NotFound from "./pages/NotFound";
import Login from "./components/Login";
import Signup from "./components/Signup";
import Dashboard from "./components/Dashboard";
import PendingUser from "./components/PendingUser";
import EnvDebug from "./components/EnvDebug";

interface User {
  id: number;
  username: string;
  email: string;
  status?: string;
  role?: string;
  last_login: string;
}

const App = () => {
  const [user, setUser] = useState<User | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Check if user is already logged in (from localStorage)
    const savedUser = localStorage.getItem('qfast_user');
    if (savedUser) {
      try {
        const parsedUser = JSON.parse(savedUser);
        setUser(parsedUser);
        setIsAuthenticated(true);
      } catch (error) {
        console.error('Error parsing saved user:', error);
        localStorage.removeItem('qfast_user');
      }
    }
    setIsLoading(false);
  }, []);

  const handleLoginSuccess = (userData: User) => {
    setUser(userData);
    setIsAuthenticated(true);
    localStorage.setItem('qfast_user', JSON.stringify(userData));
  };

  const handleSignupSuccess = () => {
    // After successful signup, user will be redirected to login
    // The Login component will handle the flow
  };

  const handleLogout = () => {
    setUser(null);
    setIsAuthenticated(false);
    localStorage.removeItem('qfast_user');
  };

  const handleEnterApp = () => {
    // Navigate to the main application
    window.location.href = '/app';
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <BrowserRouter>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <Routes>
          {/* Authentication Routes */}
          <Route
            path="/login"
            element={
              isAuthenticated ? (
                <Navigate to="/dashboard" replace />
              ) : (
                <Login
                  onLoginSuccess={handleLoginSuccess}
                  onSwitchToSignup={() => window.location.href = '/signup'}
                />
              )
            }
          />
          <Route
            path="/signup"
            element={
              isAuthenticated ? (
                <Navigate to="/dashboard" replace />
              ) : (
                <Signup
                  onSignupSuccess={handleSignupSuccess}
                  onSwitchToLogin={() => window.location.href = '/login'}
                />
              )
            }
          />

          {/* Protected Routes */}
          <Route
            path="/dashboard"
            element={
              isAuthenticated ? (
                user!.status === 'Pending' ? (
                  <PendingUser
                    user={user!}
                    onLogout={handleLogout}
                  />
                ) : (
                  <Dashboard
                    user={user!}
                    onLogout={handleLogout}
                    onEnterApp={handleEnterApp}
                  />
                )
              ) : (
                <Navigate to="/login" replace />
              )
            }
          />

          {/* Main Application Route */}
          <Route
            path="/app"
            element={
              isAuthenticated ? (
                <Index />
              ) : (
                <Navigate to="/login" replace />
              )
            }
          />

          {/* Default Route */}
          <Route
            path="/"
            element={
              isAuthenticated ? (
                <Navigate to="/dashboard" replace />
              ) : (
                <Navigate to="/login" replace />
              )
            }
          />

          <Route path="*" element={<NotFound />} />
        </Routes>
      </TooltipProvider>
    </BrowserRouter>
  );
};

export default App;
