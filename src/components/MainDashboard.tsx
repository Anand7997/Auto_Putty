import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  ClipboardList,
  Lightbulb,
  Code2,
  Play,
  BarChart3,
  Settings,
  ArrowRight,
  CheckCircle2,
  Clock,
  Target,
  Users,
  FunctionSquare,
  AlertTriangle
} from 'lucide-react';

// Import existing components that will be used in each tab
import AutomationPlanningDashboard from './AutomationPlanningDashboard';
import AutomationDevelopmentDashboard from './AutomationDevelopmentDashboard';
import TestExecutionDashboard from './TestExecutionDashboard';
import ReportingDashboard from './ReportingDashboard';
import RequirementsAnalysisDashboard from './RequirementsAnalysisDashboard';
import { MaintenanceDashboard } from './MaintenanceDashboard';
import { useAuthorization } from '@/hooks/useAuthorization';


interface User {
  id: number;
  username: string;
  email: string;
  role?: string;
  status?: string;
  last_login: string;
}

interface MainDashboardProps {
  onFunctionSelect?: (func: any) => void;
}

type TabType = 'Home' | 'requirements' | 'planning' | 'development' | 'execution' | 'reporting' | 'maintenance';

const MainDashboard: React.FC<MainDashboardProps> = ({ onFunctionSelect }) => {
  const [activeTab, setActiveTab] = useState<TabType>('Home');
  const [navigationData, setNavigationData] = useState<any>(null);
  const [currentUser, setCurrentUser] = useState<User | null>(null);

  // Authorization checks for each function
  const requirementsAuth = useAuthorization('requirements');
  const planningAuth = useAuthorization('planning');
  const developmentAuth = useAuthorization('development');
  const testLabAuth = useAuthorization('test-lab');
  const reportingAuth = useAuthorization('reporting');
  const maintenanceAuth = useAuthorization('maintenance');

  // Load current user from localStorage
  useEffect(() => {
    const savedUser = localStorage.getItem('qfast_user');
    if (savedUser) {
      try {
        const parsedUser = JSON.parse(savedUser);
        setCurrentUser(parsedUser);
      } catch (error) {
        console.error('Error parsing saved user:', error);
      }
    }
  }, []);

  // Listen for navigation events from development dashboard
  React.useEffect(() => {
    const handleNavigateToPlanning = (event: any) => {
      setActiveTab('planning');
      if (event.detail) {
        setNavigationData(event.detail);
      }
    };

    window.addEventListener('navigateToPlanning', handleNavigateToPlanning);
    return () => {
      window.removeEventListener('navigateToPlanning', handleNavigateToPlanning);
    };
  }, []);

  const renderTabContent = () => {
    switch (activeTab) {
      case 'Home':
        return renderHomeContent();
      case 'requirements':
        if (!requirementsAuth.authorized && !requirementsAuth.loading) {
          return renderUnauthorizedContent('Requirements & Feasibility Analysis');
        }
        return renderRequirementsContent();
      case 'planning':
        if (!planningAuth.authorized && !planningAuth.loading) {
          return renderUnauthorizedContent('Automation Planning');
        }
        return <AutomationPlanningDashboard onBack={() => setActiveTab('Home')} navigationData={navigationData} />;
      case 'development':
        if (!developmentAuth.authorized && !developmentAuth.loading) {
          return renderUnauthorizedContent('Automation Development');
        }
        return <AutomationDevelopmentDashboard onBack={() => setActiveTab('Home')} />;
      case 'execution':
        if (!testLabAuth.authorized && !testLabAuth.loading) {
          return renderUnauthorizedContent('Test Lab');
        }
        return <TestExecutionDashboard />;
      case 'reporting':
        if (!reportingAuth.authorized && !reportingAuth.loading) {
          return renderUnauthorizedContent('Reporting');
        }
        return <ReportingDashboard />;
      case 'maintenance':
        if (!maintenanceAuth.authorized && !maintenanceAuth.loading) {
          return renderUnauthorizedContent('Maintenance');
        }
        return renderMaintenanceContent();
      default:
        return renderHomeContent();
    }
  };

  const renderHomeContent = () => (
    <div className="space-y-6">
      {/* Header */}
      <div className="text-center space-y-4">
        <h1 className="text-4xl font-bold text-gray-900">Automation Pro Suite</h1>
        <p className="text-lg text-gray-600">Comprehensive Test Automation Lifecycle Management</p>
      </div>

      {/* User Dashboard Button */}
      {currentUser && (
        <div className="flex justify-end mt-4">
          <Button
            onClick={() => window.location.href = `${window.location.origin}/dashboard`}
            className="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-2 rounded-lg flex items-center space-x-2"
          >
            <Users className="w-4 h-4" />
            <span>My Dashboard</span>
          </Button>
        </div>
      )}

      {/* Main Navigation Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Requirements Card */}
        <Card
          className={`transition-all duration-300 bg-gradient-to-br from-blue-50 to-indigo-100 border-blue-200 hover:border-blue-300 ${
            requirementsAuth.loading ? 'cursor-wait opacity-50' :
            !requirementsAuth.authorized ? 'cursor-not-allowed opacity-50' : 'cursor-pointer hover:shadow-lg'
          }`}
          onClick={() => {
            if (!requirementsAuth.loading && requirementsAuth.authorized) {
              setActiveTab('requirements');
            }
          }}
        >
          <CardHeader className="pb-3">
            <div className="flex items-center space-x-3">
              <div className="w-12 h-12 bg-blue-500 rounded-lg flex items-center justify-center">
                <ClipboardList className="w-6 h-6 text-white" />
              </div>
              <div>
                <CardTitle className="text-lg text-gray-900">Requirements & Feasibility Analysis</CardTitle>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-gray-600 text-sm mb-4">
              Define requirements, assess feasibility, and validate automation scope
            </p>
            <div className="flex items-center justify-between">
              <Badge variant="secondary" className="bg-blue-100 text-blue-700">Phase 1</Badge>
              <ArrowRight className="w-4 h-4 text-blue-500" />
            </div>
          </CardContent>
        </Card>

        {/* Planning Card */}
        <Card
          className={`transition-all duration-300 bg-gradient-to-br from-green-50 to-emerald-100 border-green-200 hover:border-green-300 ${
            planningAuth.loading ? 'cursor-wait opacity-50' :
            !planningAuth.authorized ? 'cursor-not-allowed opacity-50' : 'cursor-pointer hover:shadow-lg'
          }`}
          onClick={() => {
            if (!planningAuth.loading && planningAuth.authorized) {
              setActiveTab('planning');
            }
          }}
        >
          <CardHeader className="pb-3">
            <div className="flex items-center space-x-3">
              <div className="w-12 h-12 bg-green-500 rounded-lg flex items-center justify-center">
                <Lightbulb className="w-6 h-6 text-white" />
              </div>
              <div>
                <CardTitle className="text-lg text-gray-900">Automation Planning</CardTitle>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-gray-600 text-sm mb-4">
              Create projects, define modules, and organize test cases structure
            </p>
            <div className="flex items-center justify-between">
              <Badge variant="secondary" className="bg-green-100 text-green-700">Phase 2</Badge>
              <ArrowRight className="w-4 h-4 text-green-500" />
            </div>
          </CardContent>
        </Card>

        {/* Development Card */}
        <Card
          className={`transition-all duration-300 bg-gradient-to-br from-purple-50 to-violet-100 border-purple-200 hover:border-purple-300 ${
            developmentAuth.loading ? 'cursor-wait opacity-50' :
            !developmentAuth.authorized ? 'cursor-not-allowed opacity-50' : 'cursor-pointer hover:shadow-lg'
          }`}
          onClick={() => {
            if (!developmentAuth.loading && developmentAuth.authorized) {
              setActiveTab('development');
            }
          }}
        >
          <CardHeader className="pb-3">
            <div className="flex items-center space-x-3">
              <div className="w-12 h-12 bg-purple-500 rounded-lg flex items-center justify-center">
                <Code2 className="w-6 h-6 text-white" />
              </div>
              <div>
                <CardTitle className="text-lg text-gray-900">Automation Development</CardTitle>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-gray-600 text-sm mb-4">
              Build test steps, create automation scripts, and develop test cases
            </p>
            <div className="flex items-center justify-between">
              <Badge variant="secondary" className="bg-purple-100 text-purple-700">Phase 3</Badge>
              <ArrowRight className="w-4 h-4 text-purple-500" />
            </div>
          </CardContent>
        </Card>

        {/* Execution Card */}
        <Card
          className={`transition-all duration-300 bg-gradient-to-br from-orange-50 to-amber-100 border-orange-200 hover:border-orange-300 ${
            testLabAuth.loading ? 'cursor-wait opacity-50' :
            !testLabAuth.authorized ? 'cursor-not-allowed opacity-50' : 'cursor-pointer hover:shadow-lg'
          }`}
          onClick={() => {
            if (!testLabAuth.loading && testLabAuth.authorized) {
              setActiveTab('execution');
            }
          }}
        >
          <CardHeader className="pb-3">
            <div className="flex items-center space-x-3">
              <div className="w-12 h-12 bg-orange-500 rounded-lg flex items-center justify-center">
                <Play className="w-6 h-6 text-white" />
              </div>
              <div>
                <CardTitle className="text-lg text-gray-900">Test Lab</CardTitle>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-gray-600 text-sm mb-4">
              Execute test suites, run automation scripts, and monitor test runs
            </p>
            <div className="flex items-center justify-between">
              <Badge variant="secondary" className="bg-orange-100 text-orange-700">Phase 4</Badge>
              <ArrowRight className="w-4 h-4 text-orange-500" />
            </div>
          </CardContent>
        </Card>

        {/* Reporting Card */}
        <Card
          className={`transition-all duration-300 bg-gradient-to-br from-pink-50 to-rose-100 border-pink-200 hover:border-pink-300 ${
            reportingAuth.loading ? 'cursor-wait opacity-50' :
            !reportingAuth.authorized ? 'cursor-not-allowed opacity-50' : 'cursor-pointer hover:shadow-lg'
          }`}
          onClick={() => {
            if (!reportingAuth.loading && reportingAuth.authorized) {
              setActiveTab('reporting');
            }
          }}
        >
          <CardHeader className="pb-3">
            <div className="flex items-center space-x-3">
              <div className="w-12 h-12 bg-pink-500 rounded-lg flex items-center justify-center">
                <BarChart3 className="w-6 h-6 text-white" />
              </div>
              <div>
                <CardTitle className="text-lg text-gray-900">Reporting</CardTitle>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-gray-600 text-sm mb-4">
              View execution results, generate reports, and analyze test outcomes
            </p>
            <div className="flex items-center justify-between">
              <Badge variant="secondary" className="bg-pink-100 text-pink-700">Phase 5</Badge>
              <ArrowRight className="w-4 h-4 text-pink-500" />
            </div>
          </CardContent>
        </Card>

        {/* Maintenance Card */}
        <Card
          className={`transition-all duration-300 bg-gradient-to-br from-gray-50 to-slate-100 border-gray-200 hover:border-gray-300 ${
            maintenanceAuth.loading ? 'cursor-wait opacity-50' :
            !maintenanceAuth.authorized ? 'cursor-not-allowed opacity-50' : 'cursor-pointer hover:shadow-lg'
          }`}
          onClick={() => {
            if (!maintenanceAuth.loading && maintenanceAuth.authorized) {
              setActiveTab('maintenance');
            }
          }}
        >
          <CardHeader className="pb-3">
            <div className="flex items-center space-x-3">
              <div className="w-12 h-12 bg-gray-500 rounded-lg flex items-center justify-center">
                <Settings className="w-6 h-6 text-white" />
              </div>
              <div>
                <CardTitle className="text-lg text-gray-900">Maintenance</CardTitle>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-gray-600 text-sm mb-4">
              Update tests, maintain scripts, and manage automation framework
            </p>
            <div className="flex items-center justify-between">
              <Badge variant="secondary" className="bg-gray-100 text-gray-700">Phase 6</Badge>
              <ArrowRight className="w-4 h-4 text-gray-500" />
            </div>
          </CardContent>
        </Card>
      </div>



    </div>
  );

  const renderRequirementsContent = () => (
    <div className="space-y-6">
      <RequirementsAnalysisDashboard onBack={() => setActiveTab('Home')} onFunctionSelect={onFunctionSelect} />
    </div>
  );

  const renderMaintenanceContent = () => (
    <div className="space-y-6">
      <MaintenanceDashboard />
    </div>
  );

  const renderUnauthorizedContent = (functionName: string) => (
    <div className="space-y-6">
      <Card className="bg-white backdrop-blur-sm border-red-200">
        <CardHeader>
          <CardTitle className="text-2xl text-red-900 flex items-center">
            <AlertTriangle className="w-6 h-6 mr-2" />
            Access Denied
          </CardTitle>
          <p className="text-red-600">You do not have permission to access this function</p>
        </CardHeader>
        <CardContent className="space-y-6">
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>
              You are not authorized to access the <strong>{functionName}</strong> function.
              Please contact your administrator to request access.
            </AlertDescription>
          </Alert>
          <div className="text-center py-8">
            <p className="text-gray-600 mb-4">
              Only users assigned to this function by an administrator can access it.
            </p>
            <Button
              onClick={() => setActiveTab('Home')}
              className="bg-gray-500 hover:bg-gray-600"
            >
              Back to Home
              <ArrowRight className="w-4 h-4 ml-2" />
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-white to-gray-100">
      <div className="container mx-auto px-6 py-8">
        {/* Top Navigation Tabs */}
        <div className="mb-8">
          <div className="flex flex-wrap gap-2 bg-white p-2 rounded-lg shadow-sm border border-gray-200">
            {[
              { key: 'Home', label: 'Home', icon: Target },
              { key: 'requirements', label: 'Requirements & Feasibility', icon: ClipboardList },
              { key: 'planning', label: 'Automation Planning', icon: Lightbulb },
              { key: 'development', label: 'Automation Development', icon: Code2 },
              { key: 'execution', label: 'Test Execution', icon: Play },
              { key: 'reporting', label: 'Reporting', icon: BarChart3 },
              { key: 'maintenance', label: 'Maintenance', icon: Settings }
            ].map(({ key, label, icon: Icon }) => {
              // Check authorization for each tab
              let isAuthorized = true;
              let isLoading = false;

              if (key === 'requirements') {
                isAuthorized = requirementsAuth.authorized;
                isLoading = requirementsAuth.loading;
              } else if (key === 'planning') {
                isAuthorized = planningAuth.authorized;
                isLoading = planningAuth.loading;
              } else if (key === 'development') {
                isAuthorized = developmentAuth.authorized;
                isLoading = developmentAuth.loading;
              } else if (key === 'execution') {
                isAuthorized = testLabAuth.authorized;
                isLoading = testLabAuth.loading;
              } else if (key === 'reporting') {
                isAuthorized = reportingAuth.authorized;
                isLoading = reportingAuth.loading;
              } else if (key === 'maintenance') {
                isAuthorized = maintenanceAuth.authorized;
                isLoading = maintenanceAuth.loading;
              }

              return (
                <Button
                  key={key}
                  variant={activeTab === key ? 'default' : 'ghost'}
                  onClick={() => {
                    if (!isLoading && isAuthorized) {
                      setActiveTab(key as TabType);
                    }
                  }}
                  disabled={isLoading || !isAuthorized}
                  className={`flex items-center space-x-2 text-sm ${
                    activeTab === key
                      ? 'bg-blue-500 text-white hover:bg-blue-600'
                      : isLoading
                        ? 'text-gray-400 cursor-wait'
                        : !isAuthorized
                          ? 'text-red-400 cursor-not-allowed'
                          : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  <span className="hidden sm:inline">{label}</span>
                  {!isAuthorized && !isLoading && <span className="text-xs">🔒</span>}
                </Button>
              );
            })}
          </div>
        </div>

        {/* Tab Content */}
        <div className="w-full">
          {renderTabContent()}
        </div>
      </div>
    </div>
  );
};

export default MainDashboard;
