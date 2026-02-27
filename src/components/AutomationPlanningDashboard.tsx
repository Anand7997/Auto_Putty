import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ArrowLeft, FolderPlus, Lightbulb, Target, AlertTriangle, RefreshCw } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { useAuthorization } from '@/hooks/useAuthorization';

// Import existing components
import ProjectDashboard from './ProjectDashboard';
import ModulesDashboard from './ModulesDashboard';
import TestCaseDashboard from './TestCaseDashboard';

type PlanningViewType = 'overview' | 'projects' | 'modules' | 'testcases';

interface AutomationPlanningDashboardProps {
  onBack?: () => void;
  navigationData?: {
    navigateToTestCases?: boolean;
    projectId?: number;
    moduleId?: number;
    savedTestCase?: string;
    message?: string;
  };
}

const AutomationPlanningDashboard: React.FC<AutomationPlanningDashboardProps> = ({ onBack, navigationData }) => {
  const [currentView, setCurrentView] = useState<PlanningViewType>('overview');
  const [selectedProject, setSelectedProject] = useState<any>(null);
  const [selectedModule, setSelectedModule] = useState<any>(null);

  // Check authorization for planning function
  const { authorized, loading: authLoading, error: authError } = useAuthorization('planning');

  const { toast } = useToast();

  // Handle navigation from development dashboard
  React.useEffect(() => {
    if (navigationData?.navigateToTestCases && navigationData.projectId && navigationData.moduleId) {
      // Auto-navigate to test cases view
      // First, we need to fetch the project and module data
      fetchProjectAndModule(navigationData.projectId, navigationData.moduleId);
    }
  }, [navigationData]);

  const fetchProjectAndModule = async (projectId: number, moduleId: number) => {
    try {
      // Fetch project data
      const projectResponse = await fetch(`http://localhost:5000/api/projects/${projectId}`);
      if (projectResponse.ok) {
        const project = await projectResponse.json();
        setSelectedProject(project);
        
        // Fetch module data
        const moduleResponse = await fetch(`http://localhost:5000/api/modules/${moduleId}`);
        if (moduleResponse.ok) {
          const module = await moduleResponse.json();
          setSelectedModule(module);
          setCurrentView('testcases');
          
          // Show success message for sync from development
          if (navigationData?.message) {
            setTimeout(() => {
              toast({
                title: "🎯 Automation Planning Sync Complete",
                description: navigationData.message,
              });
            }, 500);
          }
        }
      }
    } catch (error) {
      console.error('Error fetching project/module data:', error);
      // Fallback to overview if fetch fails
      setCurrentView('overview');
    }
  };

  const handleProjectSelect = (project: any) => {
    setSelectedProject(project);
    setCurrentView('modules');
  };

  const handleModuleSelect = (module: any) => {
    setSelectedModule(module);
    setCurrentView('testcases');
  };

  const renderBreadcrumb = () => {
    const items = [];
    
    items.push({ label: 'Automation Planning', onClick: () => setCurrentView('overview') });
    
    if (currentView === 'projects' || selectedProject) {
      items.push({ label: 'Projects', onClick: () => setCurrentView('projects') });
    }
    
    if (selectedProject && (currentView === 'modules' || selectedModule)) {
      items.push({ 
        label: selectedProject.name, 
        onClick: () => setCurrentView('modules') 
      });
    }
    
    if (selectedModule && currentView === 'testcases') {
      items.push({ 
        label: selectedModule.name, 
        onClick: () => setCurrentView('testcases') 
      });
    }

    return (
      <div className="flex items-center space-x-2 text-sm text-gray-600 mb-6">
        {items.map((item, index) => (
          <React.Fragment key={index}>
            <button
              onClick={item.onClick}
              className="hover:text-blue-600 hover:underline"
            >
              {item.label}
            </button>
            {index < items.length - 1 && <span>/</span>}
          </React.Fragment>
        ))}
      </div>
    );
  };

  const renderOverview = () => (
    <div className="space-y-6">
      <Card className="bg-white backdrop-blur-sm border-gray-200">
        <CardHeader>
          <div className="flex items-center space-x-3">
            <div className="w-12 h-12 bg-green-500 rounded-lg flex items-center justify-center">
              <Lightbulb className="w-6 h-6 text-white" />
            </div>
            <div>
              <CardTitle className="text-2xl text-gray-900">Automation Planning</CardTitle>
              <p className="text-gray-600">Organize your automation projects, modules, and test cases</p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Projects Card */}
            <Card 
              className="cursor-pointer hover:shadow-lg transition-all duration-300 bg-gradient-to-br from-blue-50 to-indigo-100 border-blue-200 hover:border-blue-300"
              onClick={() => setCurrentView('projects')}
            >
              <CardHeader className="pb-3">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 bg-blue-500 rounded-lg flex items-center justify-center">
                    <FolderPlus className="w-5 h-5 text-white" />
                  </div>
                  <CardTitle className="text-lg text-gray-900">Projects</CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-gray-600 text-sm mb-4">
                  Create and manage automation projects. Organize your test automation efforts by project.
                </p>
                <Button size="sm" className="bg-blue-500 hover:bg-blue-600">
                  Manage Projects
                </Button>
              </CardContent>
            </Card>

            {/* Modules Card */}
            <Card className="bg-gradient-to-br from-green-50 to-emerald-100 border-green-200">
              <CardHeader className="pb-3">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 bg-green-500 rounded-lg flex items-center justify-center">
                    <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 20 20">
                      <path d="M7 3a1 1 0 000 2h6a1 1 0 100-2H7zM4 7a1 1 0 011-1h10a1 1 0 110 2H5a1 1 0 01-1-1zM2 11a2 2 0 012-2h12a2 2 0 012 2v4a2 2 0 01-2 2H4a2 2 0 01-2-2v-4z" />
                    </svg>
                  </div>
                  <CardTitle className="text-lg text-gray-900">Modules</CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-gray-600 text-sm mb-4">
                  Organize test cases into logical modules within projects for better structure.
                </p>
                <p className="text-sm text-green-600 font-medium">Select a project first</p>
              </CardContent>
            </Card>

            {/* Test Cases Card */}
            <Card className="bg-gradient-to-br from-purple-50 to-violet-100 border-purple-200">
              <CardHeader className="pb-3">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 bg-purple-500 rounded-lg flex items-center justify-center">
                    <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M3 4a1 1 0 011-1h4a1 1 0 010 2H6.414l2.293 2.293a1 1 0 01-1.414 1.414L5 6.414V8a1 1 0 01-2 0V4zm9 1a1 1 0 110-2h4a1 1 0 011 1v4a1 1 0 11-2 0V6.414l-2.293 2.293a1 1 0 11-1.414-1.414L13.586 5H12zm-9 7a1 1 0 112 0v1.586l2.293-2.293a1 1 0 111.414 1.414L6.414 15H8a1 1 0 110 2H4a1 1 0 01-1-1v-4zm13-1a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 110-2h1.586l-2.293-2.293a1 1 0 111.414-1.414L15 13.586V12a1 1 0 011-1z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <CardTitle className="text-lg text-gray-900">Test Cases</CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-gray-600 text-sm mb-4">
                  View and manage test cases created by the Automation Development phase.
                </p>
                <p className="text-sm text-purple-600 font-medium">Select a module first</p>
              </CardContent>
            </Card>
          </div>


        </CardContent>
      </Card>
    </div>
  );

  const renderContent = () => {
    switch (currentView) {
      case 'overview':
        return renderOverview();
      case 'projects':
        return (
          <div className="space-y-4">
            <ProjectDashboard 
              onProjectSelect={handleProjectSelect}
              onBack={() => setCurrentView('overview')}
              showBackButton={true}
            />
          </div>
        );
      case 'modules':
        return (
          <div className="space-y-4">
            <ModulesDashboard 
              selectedProject={selectedProject}
              onModuleSelect={handleModuleSelect}
              onBack={() => setCurrentView('projects')}
            />
          </div>
        );
      case 'testcases':
        return (
          <div className="space-y-4">
            <TestCaseDashboard 
              selectedProject={selectedProject}
              selectedModule={selectedModule}
              onBack={() => setCurrentView('modules')}
              readOnlyMode={true} // This makes it show test cases created by development
              highlightTestCase={navigationData?.savedTestCase} // Highlight newly synced test case
              onTestCaseSelect={(testCase) => {
                // Handle test case selection to show test steps
                console.log('Selected test case:', testCase);
              }}
            />
          </div>
        );
      default:
        return renderOverview();
    }
  };

  // Show loading while checking authorization
  if (authLoading) {
    return (
      <Card className="bg-white backdrop-blur-sm border-gray-200">
        <CardContent className="p-8 text-center">
          <div className="flex items-center justify-center space-x-2 text-gray-600">
            <RefreshCw className="w-5 h-5 animate-spin" />
            <span>Checking authorization...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Show error if authorization check failed
  if (authError) {
    return (
      <Card className="bg-white backdrop-blur-sm border-gray-200">
        <CardContent className="p-8 text-center">
          <div className="text-center">
            <AlertTriangle className="w-12 h-12 text-red-500 mx-auto mb-4" />
            <p className="text-red-600">Error checking authorization: {authError}</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Show access denied if not authorized
  if (!authorized) {
    return (
      <Card className="bg-white backdrop-blur-sm border-gray-200">
        <CardContent className="p-8 text-center">
          <div className="text-center">
            <AlertTriangle className="w-12 h-12 text-red-500 mx-auto mb-4" />
            <h2 className="text-2xl font-bold text-gray-900 mb-2">Access Denied</h2>
            <p className="text-gray-600">You are not allowed to access this function.</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header with Back Button */}
      <div className="flex items-center justify-between">
        {renderBreadcrumb()}
        <div className="flex items-center gap-2">
          {onBack && (
            <button
              onClick={onBack}
              className="justify-center gap-2 whitespace-nowrap rounded-md font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0 h-10 px-4 py-2 flex items-center space-x-2 text-sm bg-blue-500 text-white hover:bg-blue-600"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-target w-4 h-4">
                <circle cx="12" cy="12" r="10"></circle>
                <circle cx="12" cy="12" r="6"></circle>
                <circle cx="12" cy="12" r="2"></circle>
              </svg>
              <span className="hidden sm:inline">Home</span>
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      {renderContent()}
    </div>
  );
};

export default AutomationPlanningDashboard;
