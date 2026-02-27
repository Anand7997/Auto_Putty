import React, { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  User,
  Mail,
  Calendar,
  LogOut,
  Database,
  Sparkles,
  Zap,
  Activity,
  BarChart3,
  Settings,
  TestTube,
  Shield,
  Users,
  FunctionSquare
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import AuthorizeUsers from './AuthorizeUsers';
import AuthorizeFunctions from './AuthorizeFunctions';

interface User {
  id: number;
  username: string;
  email: string;
  role?: string;
  last_login: string;
}

interface DashboardProps {
  user: User;
  onLogout: () => void;
  onEnterApp: () => void;
}

const Dashboard: React.FC<DashboardProps> = ({ user, onLogout, onEnterApp }) => {
  const [currentTime, setCurrentTime] = useState(new Date());
  const { toast } = useToast();

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);

    return () => clearInterval(timer);
  }, []);

  const handleLogout = () => {
    toast({
      title: "Logged Out",
      description: "You have been successfully logged out.",
    });
    onLogout();
  };

  const formatLastLogin = (lastLogin: string) => {
    try {
      const date = new Date(lastLogin);
      return date.toLocaleString();
    } catch {
      return 'Never';
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-indigo-50">
      {/* Header */}
      <div className="border-b border-gray-200 bg-white/90 backdrop-blur-sm">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 bg-gradient-to-r from-blue-500 to-indigo-500 rounded-lg flex items-center justify-center">
                <Sparkles className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-gray-900">
                  QFast Dashboard
                </h1>
                <p className="text-sm text-gray-600">
                  Welcome back, {user.username}
                </p>
              </div>
            </div>
            <div className="flex items-center space-x-4">
              <div className="text-right">
                <p className="text-sm text-gray-600">
                  {currentTime.toLocaleDateString()} {currentTime.toLocaleTimeString()}
                </p>
                <Badge variant="secondary" className="text-xs">
                  <Activity className="w-3 h-3 mr-1" />
                  Online
                </Badge>
              </div>
              <Button variant="outline" size="sm" onClick={handleLogout}>
                <LogOut className="w-4 h-4 mr-2" />
                Logout
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-6 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* User Profile Card */}
          <div className="lg:col-span-1">
            <Card className="shadow-lg">
              <CardHeader className="text-center">
                <Avatar className="w-20 h-20 mx-auto mb-4">
                  <AvatarFallback className="text-2xl font-bold bg-gradient-to-r from-blue-500 to-indigo-500 text-white">
                    {user.username.charAt(0).toUpperCase()}
                  </AvatarFallback>
                </Avatar>
                <CardTitle className="text-xl">{user.username}</CardTitle>
                <CardDescription>User ID: {user.id}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center space-x-3">
                  <Mail className="w-4 h-4 text-gray-500" />
                  <span className="text-sm">{user.email}</span>
                </div>
                <div className="flex items-center space-x-3">
                  <Calendar className="w-4 h-4 text-gray-500" />
                  <span className="text-sm">
                    Last Login: {formatLastLogin(user.last_login)}
                  </span>
                </div>
                <Separator />
                <div className="text-center space-y-2">
                  <Badge variant="default" className="bg-green-100 text-green-800">
                    <Database className="w-3 h-3 mr-1" />
                    Active User
                  </Badge>
                  {user.role && (
                    <Badge variant="secondary" className={`${user.role === 'Admin' ? 'bg-purple-100 text-purple-800' : 'bg-blue-100 text-blue-800'}`}>
                      <Shield className="w-3 h-3 mr-1" />
                      {user.role}
                    </Badge>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Main Dashboard Content */}
          <div className="lg:col-span-2">
            <Tabs defaultValue="dashboard" className="w-full">
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="dashboard">Dashboard</TabsTrigger>
                {user.role === 'Admin' && (
                  <>
                    <TabsTrigger value="users">User Management</TabsTrigger>
                    <TabsTrigger value="functions">Function Access</TabsTrigger>
                  </>
                )}
              </TabsList>

              <TabsContent value="dashboard" className="space-y-6 mt-6">
                {/* Welcome Message */}
                <Card className="shadow-lg bg-gradient-to-r from-blue-500 to-indigo-500 text-white">
                  <CardContent className="p-6">
                    <div className="flex items-center space-x-4">
                      <div className="w-12 h-12 bg-white/20 rounded-lg flex items-center justify-center">
                        <Zap className="w-6 h-6" />
                      </div>
                      <div>
                        <h2 className="text-2xl font-bold">Welcome to QFast!</h2>
                        <p className="text-blue-100">
                          Quinnox's AI-Driven Smart Testing Framework is ready for you.
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* Quick Actions */}
                <Card className="shadow-lg">
                  <CardHeader>
                    <CardTitle className="flex items-center">
                      <Settings className="w-5 h-5 mr-2" />
                      Quick Actions
                    </CardTitle>
                    <CardDescription>
                      Access the main testing framework features
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <Button
                        onClick={onEnterApp}
                        className="h-20 flex flex-col items-center justify-center space-y-2"
                        size="lg"
                      >
                        <TestTube className="w-6 h-6" />
                        <span>Enter Testing Framework</span>
                      </Button>

                      <Button
                        variant="outline"
                        className="h-20 flex flex-col items-center justify-center space-y-2"
                        size="lg"
                        disabled
                      >
                        <BarChart3 className="w-6 h-6" />
                        <span>View Analytics</span>
                        <span className="text-xs text-gray-500">(Coming Soon)</span>
                      </Button>
                    </div>
                  </CardContent>
                </Card>

                {/* System Status */}
                <Card className="shadow-lg">
                  <CardHeader>
                    <CardTitle className="flex items-center">
                      <Activity className="w-5 h-5 mr-2" />
                      System Status
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      <div className="text-center">
                        <div className="w-3 h-3 bg-green-500 rounded-full mx-auto mb-2"></div>
                        <p className="text-sm font-medium">Database</p>
                        <p className="text-xs text-gray-600">Connected</p>
                      </div>
                      <div className="text-center">
                        <div className="w-3 h-3 bg-green-500 rounded-full mx-auto mb-2"></div>
                        <p className="text-sm font-medium">Backend</p>
                        <p className="text-xs text-gray-600">Running</p>
                      </div>
                      <div className="text-center">
                        <div className="w-3 h-3 bg-green-500 rounded-full mx-auto mb-2"></div>
                        <p className="text-sm font-medium">Frontend</p>
                        <p className="text-xs text-gray-600">Active</p>
                      </div>
                      <div className="text-center">
                        <div className="w-3 h-3 bg-yellow-500 rounded-full mx-auto mb-2"></div>
                        <p className="text-sm font-medium">Tests</p>
                        <p className="text-xs text-gray-600">Ready</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </TabsContent>

              {user.role === 'Admin' && (
                <>
                  <TabsContent value="users" className="mt-6">
                    <AuthorizeUsers currentUser={user} />
                  </TabsContent>

                  <TabsContent value="functions" className="mt-6">
                    <AuthorizeFunctions onFunctionSelect={(func) => {
                      // Navigate to user management for the selected function
                      // This would need to be implemented based on the dashboard structure
                      console.log('Function selected:', func);
                    }} />
                  </TabsContent>
                </>
              )}
            </Tabs>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;